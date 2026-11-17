"""Formulario de metas: las mismas reglas valen al crear y al modificar."""
from decimal import Decimal

from django import forms

from IndicadoresApp.models import MetaDesempeno
from UsuarioApp.models import Cargo, Catalogo, Delegacion


class MetaForm(forms.Form):
    """Meta de un cargo para un ítem en el periodo vigente.
    alcance: 'GENERAL' (meta de toda la municipalidad, solo el Administrador) o el código de una delegación."""
    alcance = forms.ChoiceField(label="Alcance", required=False)  # vacío = General (o la delegación del Delegado)
    cargo = forms.ModelChoiceField(queryset=Cargo.objects.filter(estado='ACTIVO'), label="Cargo",
                                   empty_label="Seleccione un cargo...")
    item = forms.ModelChoiceField(queryset=Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id'),
                                  label="Ítem de gestión", empty_label="Seleccione un ítem...")
    valor_objetivo = forms.IntegerField(min_value=1, label="Meta del trimestre (actividades)")
    ponderador = forms.DecimalField(max_digits=5, decimal_places=2, label="Ponderador (%)")

    def __init__(self, *args, usuario=None, periodo=None, meta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.periodo = periodo
        self.usuario = usuario
        self.meta = meta  # al modificar, la meta que se edita
        if usuario is not None and usuario.es_delegado():
            # El Delegado solo define metas de su delegación
            self.fields['alcance'].choices = [(usuario.delegacion.nombre, str(usuario.delegacion))]
        else:
            opciones = [('GENERAL', 'General (toda la municipalidad)')]
            for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
                opciones.append((delegacion.nombre, f"Solo {delegacion}"))
            self.fields['alcance'].choices = opciones
        if meta is not None:
            # Al modificar no se cambia a qué cargo, ítem ni alcance pertenece: solo la meta y el ponderador
            for nombre in ['alcance', 'cargo', 'item']:
                self.fields[nombre].disabled = True
            self.initial.update({
                'alcance': meta.delegacion.nombre if meta.delegacion else 'GENERAL',
                'cargo': meta.cargo_id, 'item': meta.item_id,
                'valor_objetivo': meta.valor_objetivo, 'ponderador': meta.ponderador,
            })

    def delegacion(self):
        if self.meta is not None:
            return self.meta.delegacion
        if self.usuario is not None and self.usuario.es_delegado():
            return self.usuario.delegacion  # el Delegado siempre define metas de su delegación
        codigo = self.cleaned_data.get('alcance')
        if not codigo or codigo == 'GENERAL':
            return None
        return Delegacion.objects.filter(nombre=codigo).first()

    def clean_ponderador(self):
        ponderador = self.cleaned_data['ponderador']
        if ponderador <= 0 or ponderador > 100:
            raise forms.ValidationError("El ponderador debe ser mayor que 0 y no puede superar 100%.")
        return ponderador

    def clean(self):
        datos = super().clean()
        if self.periodo is None:
            raise forms.ValidationError("No hay un periodo vigente. Créelo en Django Admin (Periodos) antes de definir metas.")
        cargo = datos.get('cargo')
        item = datos.get('item')
        ponderador = datos.get('ponderador')
        if cargo is None or item is None or ponderador is None:
            return datos
        delegacion = self.delegacion()
        meta = self.meta
        if meta is None:
            # Si ya existe la meta de ese cargo, ítem y alcance, se actualiza en vez de duplicarse
            meta = MetaDesempeno.objects.filter(cargo=cargo, item=item, periodo=self.periodo, delegacion=delegacion).first()
        total = cargo.total_ponderadores(self.periodo, excluir=meta, delegacion=delegacion) + ponderador
        if total > 100:
            raise forms.ValidationError(f"Con esta meta los ponderadores del cargo {cargo} sumarían {total}%. "
                                        "El total no puede superar 100%.")
        self.total = total
        self.meta_existente = meta
        return datos

    def guardar(self):
        """Crea o actualiza la meta. Devuelve (meta, evento, valor anterior)."""
        datos = self.cleaned_data
        meta = self.meta_existente
        if meta is None:
            meta = MetaDesempeno(cargo=datos['cargo'], item=datos['item'], periodo=self.periodo,
                                 delegacion=self.delegacion())
            evento, antes = 'CREACION', ''
        else:
            evento, antes = 'MODIFICACION', f"{meta} = {meta.valor_objetivo} ({meta.ponderador}%)"
        meta.valor_objetivo = datos['valor_objetivo']
        meta.ponderador = Decimal(datos['ponderador'])
        meta.save()
        return meta, evento, antes


class BuscadorPersonaForm(forms.ModelForm):
    """Base de los formularios que eligen a una persona registrada escribiendo su nombre o RUT (con sugerencias de
    un <datalist>): ausencias, felicitaciones y reclamos. Quien usa el formulario entrega las personas posibles."""
    lista = 'personas'               # id del <datalist> con las sugerencias en la plantilla
    etiqueta_persona = "Funcionario"
    persona = forms.CharField(max_length=200, widget=forms.TextInput(attrs={'autocomplete': 'off',
                                                                          'placeholder': 'Escriba nombre o RUT'}))

    def __init__(self, *args, personas=None, **kwargs):
        super().__init__(*args, **kwargs)
        from UsuarioApp.models import Usuario
        self.personas = personas.order_by('first_name', 'last_name') if personas is not None else Usuario.objects.none()
        self.fields['persona'].label = self.etiqueta_persona
        self.fields['persona'].widget.attrs['list'] = self.lista

    @staticmethod
    def texto_persona(usuario):
        """Texto de cada sugerencia del buscador: nombre, RUT, perfil y delegación."""
        return f"{usuario.get_full_name() or usuario.username} · {usuario.username} · {usuario.rol()}, {usuario.delegacion or 'sin delegación'}"

    def opciones_persona(self):
        return [self.texto_persona(usuario) for usuario in self.personas]

    def clean_persona(self):
        """Acepta la sugerencia elegida, un RUT o el nombre completo (si solo una persona se llama así)."""
        import re
        texto = self.cleaned_data['persona'].strip()
        rut = re.search(r'\b\d{7,8}-[\dkK]\b', texto)
        if rut:
            encontrados = self.personas.filter(username__iexact=rut.group(0))
        else:
            nombre = texto.lower()
            encontrados = [u for u in self.personas if (u.get_full_name() or u.username).lower() == nombre]
        if len(encontrados) != 1:
            raise forms.ValidationError("Elija una persona de la lista (busque por nombre o RUT).")
        return encontrados[0]


class AusenciaForm(BuscadorPersonaForm):
    """Vacaciones, día administrativo o licencia de un funcionario o delegado. La persona se busca por nombre o RUT
    entre las que puede gestionar quien la registra (el Delegado, solo los Funcionarios de su delegación)."""
    lista = 'personas_ausencia'
    etiqueta_persona = "Funcionario o delegado"

    class Meta:
        from IndicadoresApp.models import Ausencia
        model = Ausencia
        fields = ['tipo', 'desde', 'hasta', 'observacion']
        widgets = {'desde': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}), 'hasta': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})}

    def __init__(self, *args, registrador=None, **kwargs):
        personas = registrador.usuarios_para_ausencias() if registrador is not None else None
        super().__init__(*args, personas=personas, **kwargs)
        self.order_fields(['persona', 'tipo', 'desde', 'hasta', 'observacion'])
        for nombre, campo in self.fields.items():
            campo.widget.attrs['class'] = 'form-select form-select-sm' if nombre == 'tipo' else 'form-control form-control-sm'

    def clean(self):
        datos = super().clean()
        if datos.get('desde') and datos.get('hasta') and datos['hasta'] < datos['desde']:
            self.add_error('hasta', "La fecha de término no puede ser anterior a la de inicio.")
        if datos.get('persona'):
            self.instance.usuario = datos['persona']
        return datos


class FelicitacionForm(BuscadorPersonaForm):
    """Felicitación de un usuario a un funcionario registrado. El funcionario se elige por nombre o RUT entre los
    que puede gestionar quien la registra (el Delegado, los de su delegación; el Administrador, todos)."""
    lista = 'personas_felicitacion'
    etiqueta_persona = "Funcionario felicitado"

    class Meta:
        from IndicadoresApp.models import Felicitacion
        model = Felicitacion
        fields = ['fecha', 'motivo']
        widgets = {'fecha': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}), 'motivo': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, registrador=None, periodo=None, **kwargs):
        personas = registrador.funcionarios_para_felicitaciones() if registrador is not None else None
        super().__init__(*args, personas=personas, **kwargs)
        self.periodo = periodo
        self.order_fields(['persona', 'fecha', 'motivo'])
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control form-control-sm'

    def clean(self):
        from django.utils import timezone
        datos = super().clean()
        fecha = datos.get('fecha')
        if self.periodo is None:
            raise forms.ValidationError("No hay un periodo vigente: la felicitación no tendría a qué sumar.")
        if fecha is not None and (fecha > timezone.localdate() or fecha < self.periodo.fecha_inicio):
            self.add_error('fecha', f"La fecha debe estar entre el inicio del periodo ({self.periodo.fecha_inicio:%d/%m/%Y}) y hoy.")
        if datos.get('persona'):
            self.instance.funcionario = datos['persona']
        return datos


class ReclamoForm(BuscadorPersonaForm):
    """Reclamo de un usuario sobre la atención de un funcionario. Queda Pendiente hasta que se responde."""
    lista = 'personas_reclamo'
    etiqueta_persona = "Funcionario"

    class Meta:
        from IndicadoresApp.models import Reclamo
        model = Reclamo
        fields = ['fecha', 'motivo']
        widgets = {'fecha': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}), 'motivo': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, registrador=None, **kwargs):
        personas = registrador.funcionarios_para_felicitaciones() if registrador is not None else None
        super().__init__(*args, personas=personas, **kwargs)
        self.order_fields(['persona', 'fecha', 'motivo'])
        for campo in self.fields.values():
            campo.widget.attrs['class'] = 'form-control form-control-sm'

    def clean(self):
        from django.utils import timezone
        datos = super().clean()
        if datos.get('fecha') is not None and datos['fecha'] > timezone.localdate():
            self.add_error('fecha', "La fecha del reclamo no puede ser posterior a hoy.")
        if datos.get('persona'):
            self.instance.funcionario = datos['persona']
        return datos


class RespuestaReclamoForm(forms.ModelForm):
    """Respuesta o acción tomada: al guardarla, el reclamo queda Resuelto."""
    class Meta:
        from IndicadoresApp.models import Reclamo
        model = Reclamo
        fields = ['respuesta']
        widgets = {'respuesta': forms.Textarea(attrs={'rows': 2, 'class': 'form-control form-control-sm'})}

    def clean_respuesta(self):
        respuesta = self.cleaned_data['respuesta'].strip()
        if not respuesta:
            raise forms.ValidationError("Escriba la respuesta o la acción tomada.")
        return respuesta
