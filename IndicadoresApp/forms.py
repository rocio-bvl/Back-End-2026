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
