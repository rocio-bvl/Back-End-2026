"""Guardrails del chatbot: anti prompt-injection, rate limit y saneamiento de salida.

Todo es stdlib + Django. El detector de entrada tiene dos capas deterministas y offline:

* ``normalizar`` (de ``rag``): minúsculas, sin tildes, sin puntuación.
* ``_canonico``: NFKC/NFKD, sin caracteres de ancho cero, homóglifos cirílicos/griegos,
  sustituciones tipo *leet*, letras espaciadas, repeticiones y espacios colapsados, conservando
  la puntuación.

Los patrones se dividen en ``_ALTA`` (bloqueo directo) y ``_MEDIA`` (señales). Dos señales medias
distintas también bloquean. Las preguntas definicionales ("qué es", "explica", "cómo funciona")
solo se eximen cuando no hay verbo de extracción ni referencia anafórica, para no bloquear "¿Qué
es prompt injection?" ni "¿Qué es el modo desarrollador?".

Sobre el texto se aplican además dos capacidades genéricas y offline: decodificación acotada
(base64, hexadecimal, ROT13, texto invertido y binario) y extracción indirecta/anafórica. Nada se
ejecuta ni se resuelve recursivamente; los límites están en las constantes ``_MAX_*``.

``CHATBOT_GUARDRAIL_MODO='basico'`` restaura los 9 patrones históricos (rollback sin despliegue),
sin decodificación ni historial.
"""
import base64
import binascii
import re
import time
import unicodedata
from functools import lru_cache

from django.conf import settings
from django.core.cache import cache

from ChatbotApp.rag import normalizar

MENSAJE_INYECCION = ("No puedo ayudar con esa solicitud. Puedo responder preguntas sobre el uso "
                     "del SGR y sus datos.")

# Frases imperativas típicas de un intento de manipular al asistente. Se evalúan sobre el texto
# normalizado (minúsculas, sin tildes), por eso no llevan acentos. Es la lista que usa el modo
# `basico` para el rollback exacto al comportamiento anterior.
PATRONES_INYECCION = [
    r'\bignora (todas |las )?(tus |las )?(instrucciones|reglas|indicaciones)\b',
    r'\bignora (lo|todo lo) anterior\b',
    r'\bolvida (todo |lo )?(anterior|lo que te dijeron)\b',
    r'\b(revela|muestra|dime|entrega|comparte|imprime|escribe|repite)\b.{0,40}'
    r'\b(tu prompt|tus instrucciones|system prompt|la clave|la api key|tu clave|'
    r'la contrasena del sistema|tus reglas internas)\b',
    r'\bque dice (tu|el) (prompt|system prompt)\b',
    r'\bactua (sin|como si no tuvieras) (restricciones|limites|reglas)\b',
    r'\b(modo desarrollador|modo dios|jailbreak|dan mode)\b',
    r'\bpretende (que )?(no )?(hay|tienes) restricciones\b',
    r'\b(ahora|desde ahora) (eres|seras) (un|una) [a-z]+ sin restricciones\b',
]

# --------------------------------------------------------------------------- canonicalización

# Caracteres de formato invisibles que se eliminan antes de comparar.
_FORMATO_INVISIBLE = dict.fromkeys(map(ord, '\u200b\u200c\u200d\ufeff\u00ad'), None)

# Homóglifos cirílicos y griegos básicos -> latino. Se aplican después de pasar a minúsculas.
_HOMOGLIFOS = str.maketrans({
    # cirílico
    'а': 'a', 'в': 'b', 'е': 'e', 'ё': 'e', 'к': 'k', 'м': 'm', 'н': 'h', 'о': 'o',
    'р': 'p', 'с': 'c', 'т': 't', 'у': 'y', 'х': 'x', 'і': 'i', 'ї': 'i', 'ј': 'j',
    'ѕ': 's', 'ԁ': 'd', 'һ': 'h', 'ӏ': 'l', 'ɡ': 'g',
    # griego
    'α': 'a', 'β': 'b', 'γ': 'y', 'ε': 'e', 'η': 'n', 'ι': 'i', 'κ': 'k', 'ν': 'v',
    'ο': 'o', 'ρ': 'p', 'τ': 't', 'υ': 'u', 'χ': 'x', 'ω': 'w', 'ϲ': 'c', 'ϳ': 'j',
})

# Sustituciones usadas para ofuscar palabras ("ign0ra", "1nstrucc10nes").
_LEET = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't', '8': 'b', '9': 'g',
    '@': 'a', '$': 's',
})

_PUNTUACION_ENTRE_LETRAS = re.compile(r'(?<!\w)(?:[a-zñ][._*·•\-]+){2,}[a-zñ](?!\w)')
_LETRAS_ESPACIADAS = re.compile(r'(?<!\w)(?:[a-zñ]\s){2,}[a-zñ](?!\w)')


def _unir_letras_espaciadas(texto):
    """Une secuencias de letras sueltas sin perder las fronteras entre palabras.

    Los tramos separados por dos o más espacios se consideran palabras distintas, de modo que
    ``i g n o r a   t u s`` se convierte en ``ignora tus`` y no en ``ignoratus``. Dentro de un
    tramo también se unen letras separadas por puntos u otros signos (``i.g.n.o.r.a``).
    """
    salida = []
    for parte in re.split(r'(\s{2,})', texto):
        if not parte:
            continue
        if re.fullmatch(r'\s{2,}', parte):
            salida.append(' ')
            continue
        parte = _PUNTUACION_ENTRE_LETRAS.sub(
            lambda coincidencia: re.sub(r'[._*·•\-]+', '', coincidencia.group(0)), parte,
        )
        parte = _LETRAS_ESPACIADAS.sub(
            lambda coincidencia: coincidencia.group(0).replace(' ', ''),
            parte,
        )
        salida.append(parte)
    return ''.join(salida)


def _canonico(texto):
    """Canonicalización conservadora que conserva la puntuación para no perder límites."""
    limpio = unicodedata.normalize('NFKC', str(texto or ''))
    limpio = limpio.translate(_FORMATO_INVISIBLE)
    limpio = unicodedata.normalize('NFKD', limpio)
    limpio = ''.join(caracter for caracter in limpio if not unicodedata.combining(caracter))
    limpio = limpio.lower().translate(_HOMOGLIFOS).translate(_LEET)
    limpio = _unir_letras_espaciadas(limpio)
    limpio = re.sub(r'(.)\1{2,}', r'\1', limpio)  # "ignoooooora" -> "ignora"
    limpio = re.sub(r'[ \t\r\f\v]+', ' ', limpio)
    limpio = re.sub(r'\n{2,}', '\n', limpio)
    return limpio.strip()


# --------------------------------------------------------------------------- patrones

_ALTA = [re.compile(patron, re.DOTALL) for patron in (
    # ES: imperativo + objetivo (instrucciones, reglas, restricciones...).
    r'\b(ignora|ignores|ignoren|ignorad|pasa por alto|haz caso omiso|hagan caso omiso|'
    r'no sigas|no obedezcas|no cumplas|deja de seguir|no hagas caso)\b[^\n]{0,60}'
    r'\b(tus|sus|las|los|mis|todas|todos|estas|esas|anteriores|previas|del sistema|de seguridad)?'
    r'\s*(instrucciones|reglas|indicaciones|ordenes|directrices|restricciones|filtros|politicas|'
    r'consignas|limites)\b',
    r'\b(olvida|olvides|olviden|descarta|descarte|descarten|omite|omitan|obvia|saltate|'
    r'deja de lado|dejes de lado|dejen de lado|ignora)\b[^\n]{0,50}\b(todo lo anterior|'
    r'lo anterior|instrucciones|reglas|indicaciones|ordenes|restricciones)\b',
    r'\b(ignora|olvida|descarta)\b[^\n]{0,30}\b(lo que te dijeron|lo que se te dijo|'
    r'lo que te indicaron)\b',
    r'\b(puedes|debes|tienes que|hay que|quiero que|necesito que)\b[^\n]{0,30}'
    r'\b(ignorar|olvidar|omitir|descartar)\b[^\n]{0,30}'
    r'\b(instrucciones|reglas|indicaciones|restricciones)\b',
    r'\b(no tengas en cuenta|no tomes en cuenta|no consideres|no atiendas|desconsidere|'
    r'desconsiderar|nao siga|nao sigam|nao obedeca|nao obedecam)\b[^\n]{0,40}'
    r'\b(instrucciones|reglas|indicaciones|ordenes|consignes|instrucoes|regras)\b',
    r'\b(ne tenez pas compte|ne tiens pas compte|ne pas tenir compte)\b[^\n]{0,40}'
    r'\b(instructions|regles|consignes)\b',
    r'\b(desactiva|desactivar|disable|quita|quitar|elimina|eliminar|remove)\b[^\n]{0,30}'
    r'\b(filtros|restricciones|reglas|limites|censura|seguridad)\b',
    # ES/EN/PT/FR/DE: revelar prompt, claves, contraseñas o configuración interna.
    r'\b(revela|revelame|revele|revelen|revelar|muestra|muestrame|muestre|muestren|mostrar|'
    r'dime|ensena|ensename|entrega|entregame|comparte|imprime|imprimir|escribe|repite|'
    r'expone|exponer|filtra|reveal|show|print|repeat|tell|give|display|dump|expose|'
    r'revelez|montrez|montre|affichez|afficher|mostre|zeige|zeigen|offenbare|offenbar)\b'
    r'[^\n]{0,55}\b(tu|tus|el|la|los|las|your|the|seu|sua|o|a|votre|vos|le|dein|deine|'
    r'der|die|das)?\s*(system\s*prompt|systemprompt|prompt\s+del\s+sistema|'
    r'prompt\s+do\s+sistema|prompt\s+systeme|prompt|api\s*key|apikey|clave\s+api|clave|'
    r'senha|chave|contrasena\s+del\s+sistema|password|mot\s+de\s+passe|passwort|secret|'
    r'secreto|token|credenciales|credentials|configuracion\s+interna|'
    r'configuracion\s+del\s+sistema|configuration\s+interne|interne\s+konfiguration)\b',
    r'\b(revela|revelame|revele|revelen|muestra|muestrame|muestre|mostrar|ensena|'
    r'ensename|entrega|comparte|imprime|repite|reveal|show|print|repeat|tell|give|'
    r'revelez|montrez|zeige|offenbare)\b[^\n]{0,45}\b(tu|tus|sus|your|seu|sua|votre|'
    r'vos|dein|deine)\s+(instrucciones|instructions|instrucoes|consignes|anweisungen|'
    r'reglas|rules)\b',
    r'\b(cual es|que es|what is|quelle est|was ist|qual e)\b[^\n]{0,25}\b(tu|your|seu|'
    r'votre|dein)\s+(system\s*)?(prompt|instrucciones|instructions)\b',
    r'\b(que dice|que contiene)\b[^\n]{0,25}\b(tu|el)\s+(system\s*)?prompt\b',
    r'\b(repite|repeat)\b[^\n]{0,30}\b(palabras|words)\b[^\n]{0,20}'
    r'\b(anteriores|above|previas|previous)\b',
    r'\b(repite|repetir|repeat|imprime|print)\b[^\n]{0,25}'
    r'\b(texto|mensaje|contenido|words|todo)\b[^\n]{0,20}'
    r'\b(anterior|arriba|previo|above)\b',
    r'\b(revela|revelame|muestra|muestrame|imprime|repite|escribe|entrega|comparte|'
    r'reveal|show|print|repeat)\b[^\n]{0,40}\b(instrucciones|reglas|instructions|rules)\b'
    r'[^\n]{0,15}\b(anteriores|previas|del sistema|internas|ocultas|above|previous|'
    r'hidden|system)\b',
    r'\b(cual es|que contiene|dime|muestra|revela|what is|show)\b[^\n]{0,25}'
    r'\b(configuracion interna|configuracion del sistema|internal configuration)\b',
    r'\b(quiero|necesito|deseo|i want|je veux|ich will|quero)\b[^\n]{0,15}'
    r'\b(usar|entrar|probar|activar|tener|use|enter|try|enable|utiliser|entrer|'
    r'benutzen)\b[^\n]{0,25}\b(modo\s+(desarrollador|dios|dan)|developer\s+mode|'
    r'god\s+mode|jailbreak)\b',
    # Modo desarrollador / DAN / jailbreak: activación o estado explícito, no la mera mención.
    r'\b(activa|active|activar|activado|habilita|habilitar|enable|entra|entrar|entres|'
    r'entren|ponte|pon|set|switch|inicia|iniciar)\b[^\n]{0,30}\b(modo\s+'
    r'(desarrollador|dios|dan)|developer\s+mode|god\s+mode|jailbreak)\b',
    r'\b(modo\s+(desarrollador|dios|dan)|developer\s+mode|god\s+mode)\b[^\n]{0,25}'
    r'\b(activado|activo|enabled|on|ahora|now)\b',
    r'\b(dan\s+mode|do\s+anything\s+now)\b',
    r'\b(estoy|estas|estamos|estan|you are|i am)\b[^\n]{0,20}\b(en\s+)?(modo\s+'
    r'(desarrollador|dios|dan)|developer\s+mode|jailbreak)\b',
    r'\byou are now\b[^\n]{0,30}\b(dan|developer|jailbreak|unrestricted|free|'
    r'without restrictions|no restrictions)\b',
    r'\bdu bist (jetzt|nun)\b[^\n]{0,30}\b(entwicklermodus|ohne)\b',
    # Sin restricciones, filtros o censura.
    r'\b(sin|without|no|nenhumas|aucune|ohne)\s+(restricciones|restricao|restricoes|'
    r'restrictions|filtros|filters|censura|censorship|limites|limitations|reglas|rules)\b',
    r'\bcomo si no (tuvieras|tuviera|tuvieran|hubiera|existen|existieran)\b[^\n]{0,25}'
    r'\b(restricciones|reglas|limites|filtros)\b',
    r'\b(ya no|ahora no)\s+(tienes|hay|existen)\s+(restricciones|limites|reglas|filtros)\b',
    r'\b(libre|libres)\s+de\s+(filtros|restricciones|reglas|censura)\b',
    # Cambio de rol o de identidad.
    r'\b(a partir de ahora|desde ahora|de ahora en adelante|from now on|a partir de agora|'
    r'doravante|a partir de maintenant|desormais|ab jetzt|von jetzt an)\b[^\n]{0,50}'
    r'\b(eres|seras|actua|actuas|actuaras|you are|will be|act as|voce e|sera|vous etes|'
    r'agissez|bist du|handelst)\b',
    r'\b(ahora|now)\s+(eres|seras|you are)\b[^\n]{0,35}\b(un|una|el|la|mi|a|an|the|my)?'
    r'\s*(dan|dios|libre|sin|unrestricted|without|no)\b',
    r'\b(actua|actue|actuar|act as|agis)\b[^\n]{0,25}\b(dan|sin restricciones|'
    r'without restrictions|unrestricted|jailbreak|modo desarrollador)\b',
    r'\b(pretende|pretendas|finge|fingir|simula|simular|imagina|imagine|pretend|'
    r'act as if)\b[^\n]{0,50}\b(no\s+(hay|tienes|tuvieras|existen)|sin)\b[^\n]{0,20}'
    r'\b(restricciones|reglas|limites|filtros)\b',
    # EN: ignorar/olvidar instrucciones.
    r'\b(ignore|ignores|ignorem|ignorar)\b[^\n]{0,50}\b(all\s+|any\s+|todas\s+|las\s+|'
    r'as\s+|suas\s+|your\s+|the\s+)?(previous|prior|above|earlier|anteriores|previas)?'
    r'\s*(instructions|rules|directions|guidelines|prompts|commands|instrucoes|regras|'
    r'indicacoes|instrucciones)\b',
    r'\b(disregard|override|bypass|skip|forget|forgets)\b[^\n]{0,45}\b(all\s+|any\s+|'
    r'the\s+|your\s+)?(previous|prior|above|earlier)?\s*(instructions|rules|directions|'
    r'guidelines|prompt|restrictions)\b',
    r'\b(forget|disregard|ignore)\b[^\n]{0,30}\b(everything|all|todo)\b[^\n]{0,30}'
    r'\b(above|before|previously|you were told|anterior)\b',
    r'\b(ignore|disregard|forget)\b[^\n]{0,25}\b(the\s+)?(text|content|words|context|'
    r'conversation)\b[^\n]{0,20}\b(above|before|previously|earlier)\b',
    r'\b(ignora|olvida|descarta)\b[^\n]{0,20}\b(el\s+)?(texto|mensaje|contenido|contexto)\b'
    r'[^\n]{0,15}\b(anterior|previo|de arriba)\b',
    r'\b(what are|which are|cuales son|quais sao)\b[^\n]{0,20}\b(tu|tus|your|seu|sua|'
    r'votre|vos|dein|deine)\s+(system\s*)?(instructions|instrucciones|rules|reglas|prompt)\b',
    r'\b(no respetes|no respetar|no acates|no acatar|rompe|romper|quebranta|quebrantar)\b'
    r'[^\n]{0,30}\b(reglas|instrucciones|indicaciones|restricciones|limites)\b',
    r'\b(esqueca|esquecam|esquecer)\b[^\n]{0,25}\b(tudo|todo)\b[^\n]{0,25}'
    r'\b(foi dito|anterior|precede|acima)\b',
    r'\b(oublie|oubliez|oublier)\b[^\n]{0,25}\b(tout|tous)\b[^\n]{0,25}'
    r'\b(ce qui precede|ce qui est au-dessus|precedent)\b',
    # PT: ignorar/esquecer instrucciones o reglas.
    r'\b(ignore|ignorem|ignorar)\b[^\n]{0,50}\b(todas\s+|as\s+|suas\s+)?'
    r'(instrucoes|regras|indicacoes|orientacoes)\b',
    r'\b(esqueca|esquecam|esquecer|esquece)\b[^\n]{0,45}\b(todas\s+)?(as\s+)?'
    r'(instrucoes|regras|indicacoes|orientacoes)\b',
    # FR: ignorar/olvidar instrucciones o reglas.
    r'\b(ignorez|ignorer)\b[^\n]{0,45}\b(toutes\s+)?(les\s+)?'
    r'(instructions|regles|consignes)\b',
    r'\b(oublie|oubliez|oublier)\b[^\n]{0,45}\b(toutes\s+)?(les\s+)?'
    r'(instructions|regles|consignes)\b',
    # DE: ignorar/olvidar instrucciones o reglas.
    r'\b(ignoriere|ignorieren|ignorier|missachte|missachten)\b[^\n]{0,45}'
    r'\b(alle\s+)?(vorherigen\s+)?(anweisungen|regeln|instruktionen)\b',
    r'\b(vergiss|vergessen)\b[^\n]{0,45}\b(alle\s+)?(anweisungen|regeln|instruktionen)\b',
)]

_MEDIA = [re.compile(patron, re.DOTALL) for patron in (
    r'\bsystem\s*prompt\b|\bprompt\s+del\s+sistema\b|\bprompt\s+do\s+sistema\b|'
    r'\bprompt\s+systeme\b',
    r'\b(tus|sus|your|seu|sua|votre|vos|dein|deine)\s+'
    r'(instrucciones|instructions|instrucoes|consignes|anweisungen)\b',
    r'\b(tus|sus|your|seu|sua|votre|vos|dein|deine)\s+(reglas|rules|regras|regles|regeln)\b',
    r'\bjailbreak\b',
    r'\bapi\s*key\b|\bapikey\b|\bclave\s+api\b',
    r'\bcontrasena\s+del\s+sistema\b|\bsystem\s+password\b',
    r'\bconfiguracion\s+interna\b|\binternal\s+configuration\b|'
    r'\bconfiguration\s+interne\b',
    r'\bcanario\b|\bcanary\b',
    r'\binstrucciones\s+anteriores\b|\bprevious\s+instructions\b|'
    r'\binstrucoes\s+anteriores\b|\binstructions\s+precedentes\b|'
    r'\bvorherigen\s+anweisungen\b',
    r'\bmodo\s+(desarrollador|dios|dan)\b|\bdeveloper\s+mode\b|\bgod\s+mode\b',
)]

_EXPLICATIVA = re.compile(
    r'\b(que es|que son|que significa|que significan|explica|explicame|explicar|'
    r'como funciona|como funcionan|definicion|definir|para que sirve|what is|what are|'
    r'what does|explain|how does|definition|qu est ce|c est quoi|was ist|'
    r'wie funktioniert|o que e|como funciona)\b',
    re.DOTALL,
)

# --------------------------------------------------------------------------- decodificación
# Las cargas codificadas se decodifican sin ejecutar nada. Los topes son deliberadamente bajos:
# como máximo tres textos decodificados plausibles, 4000 caracteres por texto y ocho intentos por
# familia. Un blob cuyo resultado no parece texto se descarta (ambiguo) y no aporta variante.

_MAX_DECODIFICACIONES = 3
_MAX_CARACTERES_DECODIFICADOS = 4000
# Intentos por familia antes de pasar a la siguiente. No son resultados: un blob ambiguo consume
# un intento y se descarta, de modo que dos blobs basura no impiden analizar el ataque que viene
# detrás. El número total de textos decodificados sigue acotado por _MAX_DECODIFICACIONES.
_MAX_INTENTOS_POR_TIPO = 8

_RE_BASE64 = re.compile(
    r'(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{16,}={0,2}(?![A-Za-z0-9+/=])')
# Variante URL-safe: solo se procesa si el bloque contiene "-" o "_" para no duplicar el estándar.
_RE_BASE64_URLSAFE = re.compile(
    r'(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{16,}={0,2}(?![A-Za-z0-9_=-])')
# Bloques base64 partidos en varias líneas (4 o más caracteres por línea).
_RE_BASE64_LINEAS = re.compile(
    r'(?<![A-Za-z0-9+/])(?:[A-Za-z0-9+/]{4,}[ \t]*\r?\n[ \t]*){1,}'
    r'[A-Za-z0-9+/]{4,}={0,2}(?![A-Za-z0-9+/=])')
# Tramo de dígitos hexadecimales con separadores opcionales (espacios, guiones, dos puntos, comas).
_RE_HEX = re.compile(
    r'(?<![0-9A-Fa-f])[0-9A-Fa-f][0-9A-Fa-f\s:\-,]{14,}[0-9A-Fa-f](?![0-9A-Fa-f])')
# Al menos cuatro grupos de ocho bits con separadores opcionales (espacios, comas, etc.).
_RE_BINARIO = re.compile(r'(?<!\d)[01]{8}(?:[\s:\-,]+[01]{8}){3,}(?!\d)')
# La misma carga sin separadores: 32 bits o más, múltiplo de 8.
_RE_BINARIO_CONTIGUO = re.compile(r'(?<![01])(?:[01]{8}){4,}(?![01])')
_ROT13 = str.maketrans(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz',
    'NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm',
)
_URLSAFE_A_ESTANDAR = str.maketrans('-_', '+/')


def _texto_plausible(texto):
    """Heurística barata: texto imprimible con letras suficientes, para no analizar basura."""
    if not texto:
        return False
    letras = sum(1 for caracter in texto if caracter.isalpha())
    if letras < 4:
        return False
    imprimibles = sum(
        1 for caracter in texto if caracter.isprintable() or caracter in '\n\r\t')
    return imprimibles / len(texto) >= 0.8


def _decodificar_base64(bloque, urlsafe=False):
    # Los bloques pueden venir partidos en líneas; el alfabeto URL-safe se normaliza al estándar.
    bloque = re.sub(r'\s+', '', bloque).strip()
    if len(bloque) < 16:
        return None
    if urlsafe:
        bloque = bloque.translate(_URLSAFE_A_ESTANDAR)
    relleno = (-len(bloque)) % 4
    if relleno:
        bloque += '=' * relleno
    try:
        return base64.b64decode(bloque, validate=True).decode('utf-8')
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None


def _decodificar_hex(bloque):
    limpio = re.sub(r'[\s:\-,]', '', bloque)
    if len(limpio) < 16 or len(limpio) % 2:
        return None
    try:
        return bytes.fromhex(limpio).decode('utf-8')
    except (UnicodeDecodeError, ValueError):
        return None


def _decodificar_binario(bloque):
    grupos = re.sub(r'[\s:\-,]+', ' ', bloque).strip().split()
    if len(grupos) < 4:
        return None
    try:
        return bytes(int(grupo, 2) for grupo in grupos).decode('utf-8')
    except (UnicodeDecodeError, ValueError):
        return None


def _decodificar_binario_contiguo(bloque):
    if len(bloque) < 32 or len(bloque) % 8:
        return None
    grupos = [bloque[indice:indice + 8] for indice in range(0, len(bloque), 8)]
    return _decodificar_binario(' '.join(grupos))


def _decodificaciones(texto):
    """Hasta tres textos plausibles obtenidos de cargas codificadas, sin recursión."""
    resultados = []

    def agregar(decodificado):
        if decodificado is None or len(resultados) >= _MAX_DECODIFICACIONES:
            return
        candidato = decodificado.strip()[:_MAX_CARACTERES_DECODIFICADOS]
        if _texto_plausible(candidato):
            resultados.append(candidato)

    def intentar(patron, decodificador, solo_urlsafe=False):
        intentos = 0
        for coincidencia in patron.finditer(texto):
            if len(resultados) >= _MAX_DECODIFICACIONES or intentos >= _MAX_INTENTOS_POR_TIPO:
                break
            bloque = coincidencia.group(0)
            # La variante URL-safe se reserva para bloques que realmente usan "-" o "_".
            if solo_urlsafe and '-' not in bloque and '_' not in bloque:
                continue
            intentos += 1
            agregar(decodificador(bloque))

    intentar(_RE_BASE64, _decodificar_base64)
    intentar(_RE_BASE64_LINEAS, _decodificar_base64)
    intentar(_RE_BASE64_URLSAFE,
             lambda bloque: _decodificar_base64(bloque, urlsafe=True), solo_urlsafe=True)
    intentar(_RE_HEX, _decodificar_hex)
    intentar(_RE_BINARIO, _decodificar_binario)
    intentar(_RE_BINARIO_CONTIGUO, _decodificar_binario_contiguo)

    if len(resultados) < _MAX_DECODIFICACIONES:
        agregar(texto.translate(_ROT13))
    if len(resultados) < _MAX_DECODIFICACIONES:
        agregar(texto[::-1])
    return resultados


# --------------------------------------------------------------------------- extracción y anáforas

# Verbos de extracción usados tanto por el gate explicativo como por la extracción indirecta.
# Las familias (resum-, traduc-, list-, orden-...) cubren conjugaciones y variantes de género o
# número sin enumerar cada forma; no se anclan a frases concretas de ningún corpus.
_VERBOS_EXTRACCION = (
    r'revela|revelas|revelo|revele|revelen|revelar|revelame|muestra|muestras|muestro|'
    r'muestrame|muestre|muestren|mostrar|dime|decir|ensena|ensename|entrega|entregame|'
    r'comparte|imprime|escribe|repite|expone|filtra|reveal|show|print|repeat|tell|give|'
    r'dump|expose|dame|extrae|extraer|extraiga|extraigan|resum\w*|sintetiz\w*|'
    r'traduc\w*|parafras\w*|list\w*|enumer\w*|orden\w*|reorden\w*|clasific\w*|'
    r'lee|leeme|leer|copia|transcribe|completa|completas|completos|summariz\w*|'
    r'summaris\w*|translat\w*|paraphras\w*|enumerat\w*|reorder\w*|sort|sorted|sorting'
)
_VERBO_EXTRACCION = re.compile(rf'\b(?:{_VERBOS_EXTRACCION})\b', re.DOTALL)

# Peticiones indirectas: resumir/traducir/parafrasear/listar/ordenar el contenido sensible, o
# preguntar por la configuración/entrenamiento del asistente sin un verbo de revelado explícito.
_EXTRACCION_INDIRECTA = [re.compile(patron, re.DOTALL) for patron in (
    rf'\b(?:{_VERBOS_EXTRACCION})\b(?:\s+\w+){{0,2}}\s+'
    r'(?:(?:tus|las|los|la|el|su|sus|your|the)\s+)?'
    r'(instrucciones|reglas|indicaciones|directrices|restricciones|consignas|'
    r'configuracion|parametros|prompt|system\s*prompt|manual\s+interno|politicas|'
    r'instructions|rules|guidelines|configuration|parameters)\b',
    # Verbo de extracción seguido, en la misma línea, de un posesivo y material sensible.
    rf'\b(?:{_VERBOS_EXTRACCION})\b[^\n]{{0,45}}'
    r'\b(tu|tus|your|seu|sua|votre|vos|dein|deine)\s+'
    r'(instrucciones|reglas|directrices|configuracion|parametros|prompt|'
    r'instructions|rules|guidelines|configuration|parameters)\b',
    r'\b(como|de que manera|con que|how)\b[^\n]{0,40}'
    r'\b(fuiste|fue|has sido|te han|estas|estuviste|were you|you were|are you)\b'
    r'[^\n]{0,25}\b(configurado|entrenado|programado|instruido|ajustado|'
    r'configured|trained|programmed|instructed)\b',
    r'\b(como|de que manera)\b[^\n]{0,25}\b(te|le)\b[^\n]{0,15}'
    r'\b(configuraron|entrenaron|programaron|instruyeron)\b',
    # Pregunta directa por la configuración, parámetros o instrucciones del asistente.
    r'\b(cual es|cuales son|que|dime|dame|muestra|lista|enumera|what is|which are|show|tell)\b'
    r'[^\n]{0,30}\b(tu|tus|su|sus|your|seu|sua|votre|vos|dein|deine)\s+'
    r'(configuracion|parametros|ajustes|instrucciones|reglas|directrices|prompt|'
    r'configuration|parameters|settings|instructions|rules)\b',
    # "Qué configuración/parámetros usas o tienes" (segunda persona, no una consulta del SGR).
    r'\b(que|which|cual|cuales)\b[^\n]{0,20}'
    r'\b(configuracion|parametros|ajustes|configuration|parameters|settings)\b'
    r'[^\n]{0,20}\b(usas|utilizas|tienes|aplicas|manejas|use|using)\b',
    r'\b(con que|que|cuales)\b[^\n]{0,25}\b(datos|informacion|corpus|ejemplos|textos)\b'
    r'[^\n]{0,25}\b(te|le)\b[^\n]{0,15}'
    r'(entrenaron|entreno|configuraron|programaron|instruyeron)\b',
)]

# Referencias a contenido previo. Solo bloquean cuando el historial contiene un término sensible.
_ANAFORA = [re.compile(patron, re.DOTALL) for patron in (
    r'\b(esa|esas|ese|esos|esta|estas|este|estos)\s+'
    r'(parte|partes|parametro|parametros|instruccion|instrucciones|regla|reglas|'
    r'directriz|directrices|configuracion|prompt|manual|contenido|texto|seccion|'
    r'secciones|bloque|bloques|fragmento|fragmentos|linea|lineas|dato|datos|'
    r'detalle|detalles|mensaje|mensajes|palabra|palabras)\b',
    r'\b(lo mismo|lo anterior|lo dicho|lo que (dijiste|mencionaste|indicaste|explicaste|'
    r'comentaste))\b',
    r'\b(leeme|lee|leer|dime|dame|muestra|repite|repetir|completa|completas|completos|'
    r'copia|transcribe|traduce|resume|sintetiza|parafrasea|ordena|lista|enumera)\b'
    r'[^\n]{0,35}\b(ese otro|esa otra|esos otros|esas otras|el otro|la otra|los otros|'
    r'las otras)\b',
    # "léeme eso", "dime aquello": referencia pura a lo ya mostrado.
    r'\b(leeme|lee|leer|dime|dame|muestra|repite|repetir|completa|completas|completos|'
    r'copia|transcribe|traduce|resume|sintetiza|parafrasea|ordena|lista|enumera)\b'
    r'[^\n]{0,35}\b(eso|esto|aquello|eso mismo|esto mismo)\b',
    r'\b(las|los)\s+(completas|completos)\b',
    # Verbos de extracción con pronombre enclítico: "resúmelas", "ordénalas", "dímelas".
    r'\b(?:resum|sintetiz|traduc|parafras|list|enumer|orden|reorden|clasific|copi|'
    r'transcrib|complet|dim|muestr)\w*(?:las|los|melas|melos|selas|selos)\b',
    r'\bsin resumir\b|\bsin omitir\b|\bsin censurar\b|\bsin recortar\b|'
    r'\bsin acortar\b|\bsin filtrar\b|\bintegramente\b|\btextual(?:mente)?\b',
)]

_TERMINOS_SENSIBLES = re.compile(
    r'\b(instrucciones|reglas|directrices|indicaciones|consignas|configuracion|'
    r'parametros|ajustes|prompt|system\s*prompt|manual\s+interno|politicas|restricciones|'
    r'entrenamiento|entrenad\w*|configurad\w*|programad\w*|instruid\w*|'
    r'mensaje\s+del\s+sistema|contexto\s+interno|datos\s+internos)\b',
    re.DOTALL,
)


def _tiene_anafora(texto_canonico):
    return any(patron.search(texto_canonico) for patron in _ANAFORA)



def _modo_guardrail():
    modo = getattr(settings, 'CHATBOT_GUARDRAIL_MODO', 'completo')
    return modo if modo in {'completo', 'basico'} else 'completo'


def detectar_inyeccion(texto, historial_previo=''):
    """True si el texto (o su combinación con el historial) parece prompt injection.

    La firma es retrocompatible: ``historial_previo`` es opcional. En modo ``basico`` se aplican
    solo los 9 patrones históricos sobre ``normalizar(texto)``, sin historial, para rollback.
    """
    texto = str(texto or '')
    historial_previo = str(historial_previo or '')

    if _modo_guardrail() == 'basico':
        limpio = normalizar(texto)
        if not limpio:
            return False
        return any(re.search(patron, limpio) for patron in PATRONES_INYECCION)

    if not texto.strip() and not historial_previo.strip():
        return False

    variantes_texto = [normalizar(texto), _canonico(texto)]
    # La decodificación acotada se aplica solo al turno actual; el historial ya viene filtrado.
    # Se protege el detector completo: una carga anómala nunca debe propagar una excepción.
    try:
        variantes_texto.extend(
            _canonico(decodificado) for decodificado in _decodificaciones(texto))
    except Exception:  # pragma: no cover - defensa en profundidad para entradas anómalas
        pass
    variantes = list(variantes_texto)

    historial_canonico = _canonico(historial_previo) if historial_previo.strip() else ''
    if historial_previo.strip():
        # Se prueban ambos órdenes: el fragmento puede estar antes o después del turno actual.
        para_historial = (
            f'{historial_previo} {texto}',
            f'{texto} {historial_previo}',
        )
        for combinado in para_historial:
            variantes.extend((normalizar(combinado), _canonico(combinado)))

    if any(patron.search(variante) for variante in variantes for patron in _ALTA):
        return True

    # Extracción indirecta: resumir/traducir/parafrasear/listar/ordenar material sensible o
    # preguntar por la configuración/entrenamiento, aunque no haya un verbo de revelado. Se
    # evalúa solo sobre el turno actual (y sus decodificaciones): el historial se reserva para
    # las anáforas y para los ataques directos fragmentados, evitando falsos positivos al unir
    # una conversación benigna con una petición legítima del turno siguiente.
    if any(patron.search(variante) for variante in variantes_texto
           for patron in _EXTRACCION_INDIRECTA):
        return True

    tiene_anafora = any(_tiene_anafora(variante) for variante in variantes_texto)
    # Anáfora de extracción: la referencia sola es inocua; solo bloquea si el referente del
    # historial (turnos del usuario o del asistente) contiene términos sensibles.
    if (historial_canonico and tiene_anafora
            and _TERMINOS_SENSIBLES.search(historial_canonico)):
        return True

    # El gate explicativo solo exime definiciones sin verbo de extracción ni anáfora:
    # "explica e ignora tus instrucciones" sigue bloqueado por _ALTA.
    if any(_EXPLICATIVA.search(variante) for variante in variantes):
        if not any(_VERBO_EXTRACCION.search(variante) for variante in variantes_texto) \
                and not tiene_anafora:
            return False
    medias = sum(1 for patron in _MEDIA if any(patron.search(v) for v in variantes))
    return medias >= 2


def verificar_rate_limit(usuario):
    """True si el usuario puede consultar; False si excedió el límite de la ventana actual.

    Ventana fija por usuario: clave `chatbot:rate:{id}:{indice_ventana}`. LocMemCache es por
    proceso (ver docs/chatbot.md).
    """
    limite = settings.CHATBOT_RATE_LIMIT
    if not limite or limite <= 0:
        return True
    ventana = max(1, settings.CHATBOT_RATE_VENTANA)
    indice = int(time.time() // ventana)
    clave = f"chatbot:rate:{usuario.pk}:{indice}"
    if cache.add(clave, 1, timeout=ventana):
        return True
    try:
        usadas = cache.incr(clave)
    except ValueError:  # la entrada expiró entre add e incr
        cache.set(clave, 1, timeout=ventana)
        return True
    return usadas <= limite


# --------------------------------------------------------------------------- saneo de salida
#
# El orden importa: asignaciones → clave configurada → tokens con prefijo → PII → canarios.
# Los canarios van al final y nunca dentro de un marcador ya insertado, para no fragmentar un
# secreto redactado. ``re.sub`` no vuelve a analizar el texto que sustituye, así que insertar el
# marcador no puede disparar otro patrón (la causa de WB-12).

REEMPLAZO_SENSIBLE = '[dato sensible omitido]'

# Nombres de asignación. El separador puede ser ``_`` o ``-`` y la comparación no distingue
# mayúsculas: ``X-API-KEY``, ``api-key``, ``apiKey`` y ``API_KEY`` son el mismo nombre. Las
# palabras compuestas se construyen con ``[-_]?`` para no exigir un separador donde el nombre
# camelCase no lo lleva, sin redactar texto legítimo que no sea una asignación.
_SEP_NOMBRE = r'[-_]?'
_SECRET_ACCESS_KEY = rf'SECRET{_SEP_NOMBRE}ACCESS{_SEP_NOMBRE}KEY'
_SECRET_KEY = rf'SECRET{_SEP_NOMBRE}KEY'
_API_KEY = rf'API{_SEP_NOMBRE}KEY'
_ASIGNACIONES = (
    rf'(?:CHATBOT{_SEP_NOMBRE}API{_SEP_NOMBRE}KEY|'
    rf'DB{_SEP_NOMBRE}PASSWORD|'
    rf'{_SECRET_ACCESS_KEY}|{_SECRET_KEY}|{_API_KEY}|'
    rf'CLIENT{_SEP_NOMBRE}SECRET|TOKEN|PASSWORD|PASSWD)'
)

# Valor entrecomillado (puede contener espacios y comillas escapadas) o token sin comillas.
# Para los valores sin comillas se exige un mínimo de 8 caracteres y una forma plausible de
# secreto (dígito, guion bajo o signo no alfanumérico, o al menos 16 caracteres): así
# "password: no definida" no se redacta. El valor sin comillas termina antes de ``}``, ``]`` o
# ``,`` para no consumir la estructura JSON (D3-02); los valores entre corchetes se reconocen
# como una forma propia para que ``SECRET_KEY=[A1b2C3d4E5F6]`` se redacte completo.
_CARACTERES_FIN_VALOR = r'\s"\'}\],'
_VALOR_ENTRECOMILLADO = r'(?:"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\')'
# Comilla de apertura sin cierre: se redacta hasta el final de la línea (O-03).
_VALOR_ABIERTO = r'(?:"(?:\\.|[^"\\\n])*|\'(?:\\.|[^\'\\\n])*)'
_VALOR_ENTRE_CORCHETES = r'\[[^\]\n]*\]'
_VALOR_SIN_COMILLAS = (
    rf'(?=[^{_CARACTERES_FIN_VALOR}]{{8,}})'
    rf"""(?=(?:[^{_CARACTERES_FIN_VALOR}]{{16,}}|[^{_CARACTERES_FIN_VALOR}]*"""
    rf"""(?:[\d_]|[^\w{_CARACTERES_FIN_VALOR}])[^{_CARACTERES_FIN_VALOR}]*))"""
    rf'[^{_CARACTERES_FIN_VALOR}]+'
)
_VALOR = (
    rf'(?P<valor>{_VALOR_ENTRECOMILLADO}|{_VALOR_ABIERTO}|'
    rf'{_VALOR_ENTRE_CORCHETES}|{_VALOR_SIN_COMILLAS})'
)


def _redactar_asignacion(coincidencia):
    """Redacta el valor salvo que ya sea el marcador (o un prefijo suyo).

    Si el nombre va entrecomillado (JSON: ``{"api_key": "…"}``) se conserva la estructura:
    nombre, comillas, separador y comillas del valor; solo se sustituye el valor. En el resto
    de asignaciones se sustituye toda la asignación por el marcador, como en el diseño original.
    """
    valor = coincidencia.group('valor')
    desnudo = valor
    if len(valor) >= 2 and valor[0] in '"\'' and valor[-1] == valor[0]:
        desnudo = valor[1:-1]
    if desnudo and REEMPLAZO_SENSIBLE.startswith(desnudo):
        return coincidencia.group(0)
    if coincidencia.group('cierre'):
        comilla = valor[0] if valor and valor[0] in '"\'' else ''
        return (
            f'{coincidencia.group("prefijo")}{comilla}'
            f'{REEMPLAZO_SENSIBLE}{comilla}'
        )
    return REEMPLAZO_SENSIBLE


# 1) Asignaciones primero: el valor puede ir entrecomillado y contener espacios.
# ``(?<![A-Za-z0-9])`` permite nombres compuestos con ``_``/``-`` (``DJANGO_SECRET_KEY``,
# ``MYSQL_DB_PASSWORD``, ``OPENAI_API_KEY``, ``X-API-KEY``) y sigue evitando ``XPASSWORD``.
# La raíz consume como máximo tres prefijos de hasta 16 caracteres (D3-01): un número acotado
# de repeticiones elimina el retroceso cuadrático del antiguo ``(?:[A-Za-z0-9]+_)*``. El
# ``_?`` inicial redacta también la asignación ``_SECRET_KEY`` completa. El grupo ``cierre``
# absorbe la comilla de un nombre JSON (``"api_key": "…"``).
_RAIZ_ASIGNACION = rf'_?(?:[A-Za-z0-9]{{1,16}}[-_]){{0,3}}{_ASIGNACIONES}'
_PATRONES_ASIGNACION = (
    re.compile(
        rf'(?<![A-Za-z0-9])'
        rf'(?P<prefijo>{_RAIZ_ASIGNACION}(?P<cierre>["\']?)\s*[=:]\s*)'
        rf'{_VALOR}',
        re.IGNORECASE,
    ),
)

# 2) Tokens con prefijo conocido.
_PATRONES_TOKEN = (
    re.compile(r'sk-(?:proj-|live_|test_)?[A-Za-z0-9_\-]{8,}'),
    re.compile(r'sk_(?:live|test)_[A-Za-z0-9]{8,}'),
    re.compile(r'(?:AKIA|ASIA)[0-9A-Z]{16}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9]{36,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{22,}'),
    re.compile(r'AIza[0-9A-Za-z_\-]{20,}'),
    re.compile(r'xox[baprsco]-[A-Za-z0-9\-]{10,}'),
    re.compile(r'eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}'),
    # PEM con o sin ``END``: sin cierre se redacta hasta el final del texto (O-04). El ``$``
    # solo se evalúa después de fallar ``END``. El coste en el peor caso puede ser cuadrático
    # dentro del texto pre-acotado; el tope de ``_MAX_PROCESAMIENTO`` acota la entrada, no el
    # orden de complejidad del patrón.
    re.compile(
        r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?'
        r'(?:-----END [A-Z ]*PRIVATE KEY-----|$)',
        re.IGNORECASE,
    ),
    re.compile(r'Bearer\s+[A-Za-z0-9._~+/=\-]{8,}', re.IGNORECASE),
    re.compile(
        r'(?:mysql|mariadb|postgres(?:ql)?|mongodb(?:\+srv)?|rediss|redis|sqlserver|oracle|'
        r'amqp)://[^\s"\']+',
        re.IGNORECASE),
)

# Se conserva el nombre histórico para no romper importaciones.
_PATRONES_SECRETO = _PATRONES_ASIGNACION + _PATRONES_TOKEN

# RUT chileno con DV separado por guion (cuerpo de 6 a 8 dígitos). El DV se valida localmente
# (módulo 11) en ``_redactar_rut``. Sin guion solo se redacta con etiqueta ``RUT`` y DV válido.
_RUT_RE = re.compile(
    r'\b(?P<cuerpo>\d{1,3}(?:\.?\d{3})?(?:\.?\d{3})?)-(?P<dv>[\dkK])\b')
_RUT_ETIQUETADO_RE = re.compile(
    r'(?i)\b(?P<etiqueta>rut\s*[:#]?\s*)(?P<cuerpo>\d{6,8})(?P<dv>[\dkK])\b(?!\s*-)')

# Teléfono: solo se redacta con prefijo +56/56, con separadores (espacio o guion), o precedido
# por una etiqueta. El punto no se usa como separador y nunca se redacta tras ``$``.
_RE_TELEFONO_ETIQUETADO = re.compile(
    r'(?i)\b(?P<etiqueta>(?:fono|tel[eé]fono|celular|contacto)\s*[:=#-]?\s*)'
    r'(?:\+?56[\s-]?)?(?P<numero>(?:\d[\s-]?){7,9}\d)')
_RE_TELEFONO_PREFIJO = re.compile(r'(?<![\d$])\+?56[\s-]?(?:\d[\s-]?){7,9}\d(?!\d)')
_RE_TELEFONO_SEPARADO = re.compile(
    r'(?<![\d$.])(?:9[\s-]\d{4}[\s-]\d{4}|[2-8]\d?[\s-]\d{3}[\s-]\d{4})(?![\d.])')


def _separar_canarios(valor):
    """Convierte ``CHATBOT_CANARIOS`` (CSV o lista) en una tupla sin entradas vacías."""
    if not valor:
        return ()
    if isinstance(valor, (list, tuple)):
        partes = (str(parte) for parte in valor)
    else:
        partes = str(valor).split(',')
    return tuple(parte.strip() for parte in partes if parte.strip())


@lru_cache(maxsize=16)
def _patron_canarios(canarios=''):
    """Un único patrón alternativo, con los canarios más largos primero.

    Aplicarlo en una sola pasada evita que un canario corto fragmente a otro más largo.
    """
    partes = _separar_canarios(canarios)
    if not partes:
        return None
    return re.compile('|'.join(re.escape(parte) for parte in
                               sorted(partes, key=len, reverse=True)))


def _sustituir_canarios(texto, patron):
    """Sustituye canarios fuera de los marcadores ya insertados.

    Los tramos que ya son ``REEMPLAZO_SENSIBLE`` no se vuelven a analizar: así un canario no
    puede corromper un secreto que ya fue redactado.
    """
    if patron is None:
        return texto
    return REEMPLAZO_SENSIBLE.join(
        patron.sub(REEMPLAZO_SENSIBLE, parte)
        for parte in texto.split(REEMPLAZO_SENSIBLE)
    )


def _sustituir_literal(texto, valor):
    """Sustituye un literal configurado sin tocar los marcadores ya insertados.

    Se usa la misma protección por tramos que los canarios: si la clave configurada es una
    subcadena de ``REEMPLAZO_SENSIBLE`` no puede corromperlo, y si coincide con un fragmento de
    un token, el token ya se redactó en una pasada previa.
    """
    if not valor:
        return texto
    return _sustituir_canarios(texto, re.compile(re.escape(valor)))


def _dv_rut(cuerpo):
    """Dígito verificador esperado (módulo 11) para el cuerpo numérico de un RUT."""
    suma = 0
    factor = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    if resto == 11:
        return '0'
    if resto == 10:
        return 'K'
    return str(resto)


def _redactar_rut(coincidencia):
    """Redacta solo RUT con DV válido; un DV inválido deja el texto intacto."""
    cuerpo = re.sub(r'\D', '', coincidencia.group('cuerpo'))
    digito = coincidencia.group('dv')
    if 6 <= len(cuerpo) <= 8 and digito.upper() == _dv_rut(cuerpo):
        return REEMPLAZO_SENSIBLE
    return coincidencia.group(0)


def _redactar_rut_etiquetado(coincidencia):
    """Conserva la etiqueta RUT y redacta el número si el DV es válido."""
    cuerpo = coincidencia.group('cuerpo')
    digito = coincidencia.group('dv')
    if digito.upper() == _dv_rut(cuerpo):
        return f"{coincidencia.group('etiqueta')}{REEMPLAZO_SENSIBLE}"
    return coincidencia.group(0)


def _redactar_telefono_etiquetado(coincidencia):
    """Conserva la etiqueta ("Teléfono: ") y redacta solo el número."""
    return f"{coincidencia.group('etiqueta')}{REEMPLAZO_SENSIBLE}"


def _recortar_marcador_parcial(texto):
    """Quita solo el sufijo que sea un prefijo propio de ``REEMPLAZO_SENSIBLE``.

    Se comprueban los sufijos del texto en vez de partir del último ``[``: así solo se recorta
    el prefijo literal que realmente termina el texto y nunca una redacción completa (se
    excluye el marcador entero).
    """
    mayor = min(len(REEMPLAZO_SENSIBLE) - 1, len(texto))
    for largo in range(mayor, 0, -1):
        if texto.endswith(REEMPLAZO_SENSIBLE[:largo]):
            return texto[:-largo]
    return texto


def _truncar(salida, maximo):
    """Trunca a ``maximo`` sin dejar una cola parcial del marcador de redacción."""
    if not maximo or len(salida) <= maximo:
        return salida
    # Se elimina primero el espacio final: si no, un recorte como "[dato sen " no se reconoce
    # como prefijo del marcador y ``rstrip`` dejaría visible "[dato sen".
    recortado = salida[:maximo].rstrip()
    return _recortar_marcador_parcial(recortado).rstrip()


# Tope duro de procesamiento. Acota la entrada que llega a las expresiones regulares, pero NO
# elimina el coste cuadrático de patrones como PEM con muchos ``BEGIN`` sin ``END``: solo lo
# mantiene acotado por el tamaño del texto procesado. Sin ``CHATBOT_MAX_RESPUESTA`` se procesan
# como mucho 8.000 caracteres; con máximo, el texto efectivo máximo es
# ``min(2 * máximo, 32.000)``. La salida final se sigue truncando a ``CHATBOT_MAX_RESPUESTA``
# (o queda sin truncar si el máximo es 0), por lo que el tope de 32.000 no es un límite de la
# respuesta final sino de la entrada procesada (D3-05/O-05).
_MAX_PROCESAMIENTO = 32000
_MAX_PROCESAMIENTO_SIN_MAXIMO = 8000


def sanear_salida(texto):
    """Redacta secretos y PII estructurada en una pasada y trunca la respuesta.

    Orden fijo: asignaciones → tokens con prefijo → clave configurada → PII → canarios. Los
    tokens se procesan antes de la clave literal para que una clave que sea prefijo o fragmento
    interior de un token no lo fragmente. Los canarios van al final para que no fragmenten un
    secreto que ya fue redactado. Cada sustitución es definitiva: ``re.sub`` no re-escanea el
    marcador insertado, por lo que la función es idempotente.

    El texto se acota antes de las expresiones regulares: el texto efectivo máximo es
    ``min(2 * CHATBOT_MAX_RESPUESTA, 32.000)`` o 8.000 si el máximo no está configurado. Ese
    tope acota la entrada procesada, pero no elimina el coste potencialmente cuadrático de
    patrones como PEM dentro de ese límite. Después se trunca a ``CHATBOT_MAX_RESPUESTA`` sin
    dejar una cola parcial del marcador; con máximo configurado la salida final nunca lo supera,
    y sin máximo queda acotada por el tope de 8.000. Un texto dentro del límite no se ve afectado.
    """
    limpio = str(texto or '')
    maximo = getattr(settings, 'CHATBOT_MAX_RESPUESTA', 0)
    limite_procesamiento = (
        min(maximo * 2, _MAX_PROCESAMIENTO)
        if maximo else _MAX_PROCESAMIENTO_SIN_MAXIMO
    )
    if len(limpio) > limite_procesamiento:
        limpio = _recortar_marcador_parcial(
            limpio[:limite_procesamiento].rstrip()).rstrip()

    for patron in _PATRONES_ASIGNACION:
        limpio = patron.sub(_redactar_asignacion, limpio)

    for patron in _PATRONES_TOKEN:
        limpio = patron.sub(REEMPLAZO_SENSIBLE, limpio)

    clave = getattr(settings, 'CHATBOT_API_KEY', '') or ''
    limpio = _sustituir_literal(limpio, clave)

    limpio = _RUT_RE.sub(_redactar_rut, limpio)
    limpio = _RUT_ETIQUETADO_RE.sub(_redactar_rut_etiquetado, limpio)
    limpio = _RE_TELEFONO_ETIQUETADO.sub(_redactar_telefono_etiquetado, limpio)
    limpio = _RE_TELEFONO_PREFIJO.sub(REEMPLAZO_SENSIBLE, limpio)
    limpio = _RE_TELEFONO_SEPARADO.sub(REEMPLAZO_SENSIBLE, limpio)

    canarios = getattr(settings, 'CHATBOT_CANARIOS', '') or ''
    if isinstance(canarios, (list, tuple)):
        canarios = ','.join(str(parte) for parte in canarios)
    limpio = _sustituir_canarios(limpio, _patron_canarios(canarios))
    return _truncar(limpio, maximo)
