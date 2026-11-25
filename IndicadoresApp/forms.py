"""Formulario de metas: las mismas reglas valen al crear y al modificar."""
from decimal import Decimal

from django import forms

from IndicadoresApp.models import MetaDesempeno, Ponderacion, Periodo
from UsuarioApp.models import Cargo, Catalogo, Delegacion


class PeriodoForm(forms.ModelForm):
    """RF-005 y RF-007: periodo de medición con sus fechas, días computables, umbrales del semáforo, tope de
    cumplimiento y puntos por felicitación. Lo gestionan el Coordinador y el Administrador desde Administración.
    Las reglas de fechas están en Periodo.clean(); aquí se agregan las de umbrales y que no se cruce con otro."""
    class Meta:
        model = Periodo
        fields = ['nombre', 'fecha_inicio', 'fecha_termino', 'dias_computables', 'umbral_verde', 'umbral_ambar',
                  'umbral_colectivo', 'tope_cumplimiento', 'puntos_felicitacion']
        widgets = {'fecha_inicio': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                   'fecha_termino': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def clean(self):
        datos = super().clean()
        verde, ambar = datos.get('umbral_verde'), datos.get('umbral_ambar')
        if verde is not None and ambar is not None and not 0 < ambar < verde:
            raise forms.ValidationError("El umbral ámbar debe ser mayor que 0 y menor que el umbral verde.")
        tope = datos.get('tope_cumplimiento')
        if tope is not None and tope < 100:
            raise forms.ValidationError("El tope de cumplimiento no puede ser menor que 100%.")
        inicio, termino = datos.get('fecha_inicio'), datos.get('fecha_termino')
        if inicio and termino:
            # Dos periodos que se cruzan harían ambiguo cuál es el vigente
            cruzados = Periodo.objects.filter(fecha_inicio__lte=termino, fecha_termino__gte=inicio).exclude(pk=self.instance.pk)
            if cruzados.exists():
                raise forms.ValidationError(f"Las fechas se cruzan con el periodo {cruzados.first()}.")
        return datos


class MetaForm(forms.Form):
    """Meta de un cargo para un ítem en el periodo vigente (la definen el Coordinador y el Administrador).
    alcance: 'GENERAL' (meta de toda la municipalidad) o el código de una delegación (cambia el valor objetivo de ese
    ítem solo en esa delegación). El ponderador no va aquí: es uno solo por cargo e ítem (PonderacionForm)."""
    alcance = forms.ChoiceField(label="Alcance", required=False)  # vacío = General
    cargo = forms.ModelChoiceField(queryset=Cargo.objects.filter(estado='ACTIVO'), label="Cargo",
                                   empty_label="Seleccione un cargo...")
    item = forms.ModelChoiceField(queryset=Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id'),
                                  label="Ítem de gestión", empty_label="Seleccione un ítem...")
    valor_objetivo = forms.IntegerField(min_value=1, label="Meta del trimestre (actividades)")

    def __init__(self, *args, usuario=None, periodo=None, meta=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.periodo = periodo
        self.usuario = usuario
        self.meta = meta  # al modificar, la meta que se edita
        opciones = [('GENERAL', 'General (toda la municipalidad)')]
        for delegacion in Delegacion.objects.filter(estado='ACTIVO').order_by('nombre_visible'):
            opciones.append((delegacion.nombre, f"Solo {delegacion}"))
        self.fields['alcance'].choices = opciones
        if meta is not None:
            # Al modificar no se cambia a qué cargo, ítem ni alcance pertenece: solo el valor objetivo
            for nombre in ['alcance', 'cargo', 'item']:
                self.fields[nombre].disabled = True
            self.initial.update({
                'alcance': meta.delegacion.nombre if meta.delegacion else 'GENERAL',
                'cargo': meta.cargo_id, 'item': meta.item_id, 'valor_objetivo': meta.valor_objetivo,
            })

    def delegacion(self):
        if self.meta is not None:
            return self.meta.delegacion
        codigo = self.cleaned_data.get('alcance')
        if not codigo or codigo == 'GENERAL':
            return None
        return Delegacion.objects.filter(nombre=codigo).first()

    def clean(self):
        datos = super().clean()
        if self.periodo is None:
            raise forms.ValidationError("No hay un periodo vigente. Créelo en Administración > Periodos antes de definir metas.")
        cargo = datos.get('cargo')
        item = datos.get('item')
        if cargo is None or item is None:
            return datos
        # Una meta solo tiene sentido para un ítem que ya pesa en la nota del cargo
        if not Ponderacion.objects.filter(cargo=cargo, item=item, periodo=self.periodo).exists():
            raise forms.ValidationError(f"Primero defina la ponderación de {item} para el cargo {cargo}.")
        meta = self.meta
        if meta is None:
            # Si ya existe la meta de ese cargo, ítem y alcance, se actualiza en vez de duplicarse
            meta = MetaDesempeno.objects.filter(cargo=cargo, item=item, periodo=self.periodo,
                                                delegacion=self.delegacion()).first()
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
            evento, antes = 'MODIFICACION', f"{meta} = {meta.valor_objetivo}"
        meta.valor_objetivo = datos['valor_objetivo']
        meta.save()
        return meta, evento, antes


class PonderacionForm(forms.Form):
    """Ponderación de un ítem en la nota de un cargo (RF-006). Una sola para toda la municipalidad.
    La suma del cargo no puede pasar de 100% (RN-001). Si queda bajo 100% se guarda, pero el cargo no se mide."""
    cargo = forms.ModelChoiceField(queryset=Cargo.objects.filter(estado='ACTIVO'), label="Cargo",
                                   empty_label="Seleccione un cargo...")
    item = forms.ModelChoiceField(queryset=Catalogo.objects.filter(tipo='ITEM_GESTION', estado='ACTIVO').order_by('id'),
                                  label="Ítem de gestión", empty_label="Seleccione un ítem...")
    ponderador = forms.DecimalField(max_digits=5, decimal_places=2, label="Ponderador (%)")

    def __init__(self, *args, periodo=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.periodo = periodo

    def clean_ponderador(self):
        ponderador = self.cleaned_data['ponderador']
        if ponderador <= 0 or ponderador > 100:
            raise forms.ValidationError("El ponderador debe ser mayor que 0 y no puede superar 100%.")
        return ponderador

    def clean(self):
        datos = super().clean()
        if self.periodo is None:
            raise forms.ValidationError("No hay un periodo vigente. Créelo en Administración > Periodos antes de ponderar.")
        cargo = datos.get('cargo')
        item = datos.get('item')
        ponderador = datos.get('ponderador')
        if cargo is None or item is None or ponderador is None:
            return datos
        total = cargo.total_ponderadores(self.periodo, excluir_item=item.pk) + ponderador
        if total > 100:
            raise forms.ValidationError(f"Con este ponderador el cargo {cargo} sumaría {total}%. "
                                        "El total no puede superar 100%.")
        self.total = total
        return datos

    def guardar(self):
        """Crea o actualiza la ponderación. Devuelve (ponderación, evento, valor anterior)."""
        datos = self.cleaned_data
        ponderacion = Ponderacion.objects.filter(cargo=datos['cargo'], item=datos['item'], periodo=self.periodo).first()
        if ponderacion is None:
            ponderacion = Ponderacion(cargo=datos['cargo'], item=datos['item'], periodo=self.periodo)
            evento, antes = 'CREACION', ''
        else:
            evento, antes = 'MODIFICACION', str(ponderacion)
        ponderacion.ponderador = Decimal(datos['ponderador'])
        ponderacion.save()
        return ponderacion, evento, antes


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
