from django.utils.translation import gettext_lazy as _
from decimal import Decimal, InvalidOperation
from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from django.db.models import Q
from .models import Circle, Gallery, GalleryEntry, Glaze, GlazeUse, Mold, Piece, Progress, Sample, Tag, User
from .tags import parse_tags
from .permissions import visible, can_read, sharing_circles, manageable_circles, available_materials

class DateInput(forms.DateInput):
    input_type = 'date'

    def __init__(self, attrs=None, format='%Y-%m-%d'):
        super().__init__(attrs=attrs, format=format)

class EmailAccountMixin:
    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        from django.db.models.functions import Lower, Trim
        accounts = User.objects.annotate(normalized_email=Lower(Trim('email'))).filter(normalized_email=email)
        if self.instance.pk:
            accounts = accounts.exclude(pk=self.instance.pk)
        if accounts.exists():
            raise forms.ValidationError(_('Ya existe una cuenta con este correo electrónico.'))
        return email


def account_email_field():
    return forms.EmailField(label=_('Correo electrónico'), max_length=254,
        widget=forms.EmailInput(attrs={'autocomplete':'email','inputmode':'email'}),
        help_text=_('Solo es visible en tu cuenta y para la administración.'))


class AccountForm(EmailAccountMixin, UserCreationForm):
    email = account_email_field()

    class Meta:
        model = User
        fields = ['username', 'display_name', 'email', 'password1', 'password2']
        labels = {'username': _('Usuario'), 'display_name': _('Tu nombre')}

class ProfileForm(EmailAccountMixin, forms.ModelForm):
    email = account_email_field()

    class Meta:
        model = User
        fields = ['display_name', 'email', 'bio']
        widgets = {'bio': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['display_name'].widget.attrs['autocomplete'] = 'nickname'
        self.fields['display_name'].help_text = _('Este nombre acompaña a tus piezas compartidas. Si lo dejas vacío, se muestra tu usuario.')

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class PhotosField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.update(required=False, widget=MultipleFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp', 'data-photo-input': '', 'aria-label': _('Seleccionar fotografías')}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        from PIL import Image, UnidentifiedImageError
        import warnings
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > 4:
            raise forms.ValidationError(_('Puedes subir hasta 4 fotos cada vez.'))
        for file in files:
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError(_('Cada foto debe ocupar menos de 5 MB.'))
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('error', Image.DecompressionBombWarning)
                    image = Image.open(file)
                    if image.format not in {'JPEG','PNG','WEBP'} or image.width * image.height > 30_000_000:
                        raise forms.ValidationError(_('Usa fotos JPG, PNG o WebP de hasta 30 megapíxeles.'))
                    image.verify()
                    file.seek(0)
                    with Image.open(file) as decoded:
                        decoded.load()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning, ValueError):
                raise forms.ValidationError(_('No se ha podido leer una de las imágenes.'))
            finally:
                file.seek(0)
        return files

def numeric_limits(form):
    """Expose model limits to the browser as well as server validation."""
    for name, field in form.fields.items():
        if not isinstance(field, (forms.IntegerField, forms.DecimalField)):
            continue
        model_field = form._meta.model._meta.get_field(name)
        for validator in model_field.validators:
            if not isinstance(validator, (MinValueValidator, MaxValueValidator)) or callable(validator.limit_value):
                continue
            attribute = 'min' if isinstance(validator, MinValueValidator) else 'max'
            value = validator.limit_value
            if attribute in field.widget.attrs:
                previous = Decimal(str(field.widget.attrs[attribute]))
                value = max(previous, value) if attribute == 'min' else min(previous, value)
            field.widget.attrs[attribute] = str(value)


class ResourceForm(forms.ModelForm):
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        numeric_limits(self)
        self.user = user
        if 'shared_groups' in self.fields:
            self.fields['shared_groups'].widget = forms.CheckboxSelectMultiple()
            self.fields['shared_groups'].queryset = sharing_circles(user).select_related('parent').order_by('name')
            self.fields['shared_groups'].label_from_instance = lambda obj: obj.path
            self.fields['shared_groups'].help_text = _('Los miembros podrán consultar la ficha. Solo tú podrás editarla.')
        for field in self.fields.values():
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs['rows'] = 3


def material_choice_label(obj):
    label = f'{obj.name} · {obj.get_material_type_display()}'
    if not obj.is_available:
        label += ' · ' + str(obj.get_availability_display())
    return f'{label} · {obj.group.path}' if obj.group_id else label

class PieceForm(ResourceForm):
    galleries = forms.ModelMultipleChoiceField(label=_('Añadir a galerías'), queryset=Gallery.objects.none(),
        required=False, widget=forms.SelectMultiple(attrs={'data-gallery-picker': '', 'size': 5}),
        help_text=_('Las galerías muestran la presentación pública de esta pieza. Prepara sus textos y selecciona sus fotos desde «Presentación pública».'))
    photos = PhotosField(label=_('Fotos iniciales'))
    tag_names = forms.CharField(label=_('Etiquetas'), required=False, max_length=1000,
        help_text=_('Separa las etiquetas con comas. Por ejemplo: plato, vajilla, regalo.'),
        widget=forms.TextInput(attrs={'placeholder': _('plato, vajilla, regalo'), 'data-tag-input': ''}))
    glazes = forms.ModelMultipleChoiceField(label=_('Materiales utilizados'), queryset=Glaze.objects.none(), required=False, widget=forms.CheckboxSelectMultiple())
    class Meta:
        model = Piece
        fields = ['name','started_on','stage','clay_material','technique','dimensions','weight','mold','notes','shared_groups']
        widgets = {'started_on': DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['shared_groups'].widget = forms.MultipleHiddenInput()
        if not self.is_bound:
            self.initial.setdefault('shared_groups', list(self.instance.shared_groups.values_list('pk', flat=True)) if not self.instance._state.adding else [])
        elif 'shared_groups' not in self.data and not self.instance._state.adding:
            self.fields['shared_groups'].disabled = True
        available_galleries = Gallery.objects.filter(Q(workshop__isnull=True, owner=self.user) |
            Q(workshop__in=sharing_circles(self.user))).distinct().select_related('workshop').order_by('name')
        self.fields['galleries'].queryset = available_galleries
        self.fields['galleries'].label_from_instance = lambda gallery: f'{gallery.name} · {gallery.workshop.path if gallery.workshop_id else _("Personal")}'
        if not self.instance._state.adding:
            self.initial['galleries'] = list(self.instance.gallery_entries.filter(gallery__in=available_galleries).values_list('gallery_id', flat=True))
        available_molds = available_materials(visible(Mold.objects.all(), self.user))
        previous_mold = self.instance.mold_id
        mold_visible = not previous_mold or available_molds.filter(pk=previous_mold).exists()
        if previous_mold and not mold_visible:
            available_molds = Mold.objects.filter(Q(pk__in=available_molds.values('pk')) | Q(pk=previous_mold))
        self.fields['mold'].queryset = available_molds
        self.fields['mold'].label_from_instance = lambda obj: _('Material no disponible') if obj.pk == previous_mold and not can_read(obj, self.user) else (obj.name + (' · ' + str(obj.get_availability_display()) if not obj.is_available else ''))
        if self.is_bound and previous_mold and 'mold' not in self.data:
            self.fields['mold'].disabled = True
        available_glazes = available_materials(visible(Glaze.objects.all(), self.user)).select_related('group__parent').order_by('name')
        available_clays = available_glazes.filter(material_type=Glaze.MaterialType.CLAY)
        previous_clay = self.instance.clay_material_id
        self.previous_clay_id = previous_clay
        previous_visible = not previous_clay or available_clays.filter(pk=previous_clay).exists()
        if previous_clay and not previous_visible:
            # Retain the historical link without exposing a revoked material's name.
            available_clays = Glaze.objects.filter(Q(pk__in=available_clays.values('pk')) | Q(pk=previous_clay)).select_related('group__parent').order_by('name')
        self.fields['clay_material'].queryset = available_clays
        self.fields['clay_material'].empty_label = _('Sin barro seleccionado')
        self.fields['clay_material'].label_from_instance = lambda obj: _('Material no disponible') if obj.pk == previous_clay and not can_read(obj, self.user) else material_choice_label(obj)
        self.fields['clay_material'].help_text = _('Selecciona un material de tipo barro de tu biblioteca o de tus talleres.')
        if self.is_bound and previous_clay and 'clay_material' not in self.data:
            self.fields['clay_material'].disabled = True
        self.fields['glazes'].queryset = available_glazes
        self.fields['glazes'].label_from_instance = material_choice_label
        if not self.instance._state.adding:
            self.initial.setdefault('glazes', list(self.instance.glaze_uses.filter(glaze__in=available_glazes).values_list('glaze_id', flat=True).distinct()))
            self.initial.setdefault('tag_names', ', '.join(self.instance.tags.values_list('name', flat=True)))
        self.tag_suggestions = Tag.objects.filter(pieces__in=visible(Piece.objects.all(), self.user)).distinct()[:30]
        self.fields['name'].widget.attrs.update(placeholder=_('Por ejemplo, cuenco de desayuno'), autofocus=True)
        self.fields['notes'].widget.attrs.update(placeholder=_('Qué tienes en mente, qué quieres probar…'), rows=3)
        self.fields['photos'].label = _('Fotografías')

    @property
    def coating_sections(self):
        choices = list(self['glazes'])
        return [
            {'type': category, 'title': title,
             'selected_count': sum(1 for choice in choices if choice.data['value'].instance.material_type == category and choice.data['selected']),
             'choices': [choice for choice in choices if choice.data['value'].instance.material_type == category]}
            for category, title in [('glaze', _('Esmaltes')), ('engobe', _('Engobes'))]]

    @property
    def additional_clay_choices(self):
        # Keep previously recorded secondary clays editable without duplicating
        # the primary clay selector when creating a new piece.
        return [choice for choice in self['glazes']
                if choice.data['selected'] and choice.data['value'].instance.material_type == 'clay']

    def clean_tag_names(self):
        return parse_tags(self.cleaned_data['tag_names'])

    def save(self, commit=True):
        old_link = self.previous_clay_id
        selected = self.cleaned_data.get('clay_material')
        obj = super().save(commit=False)
        if selected and can_read(selected, self.user):
            obj.clay = selected.name
        elif not selected and old_link:
            obj.clay = ''
        # Unlinked legacy free text is preserved until a material is chosen.
        if commit:
            obj.save()
            self.save_m2m()
        return obj

    def save_tags(self, piece):
        piece.tags.set([Tag.objects.get_or_create(name=name)[0] for name in self.cleaned_data['tag_names']])

    def save_glazes(self, piece):
        selected = self.cleaned_data['glazes']
        # Preserve associations to a glaze whose sharing permissions were revoked.
        piece.glaze_uses.filter(glaze__in=self.fields['glazes'].queryset).exclude(glaze__in=selected).delete()
        existing = set(piece.glaze_uses.values_list('glaze_id', flat=True))
        for glaze in selected:
            if glaze.pk not in existing:
                GlazeUse.objects.create(piece=piece, glaze=glaze, recipe_version=glaze.latest_recipe)

    def save_galleries(self, piece):
        selected = self.cleaned_data['galleries']
        if selected:
            from .models import PiecePresentation
            PiecePresentation.objects.get_or_create(piece=piece, defaults={'title': piece.name})
        piece.gallery_entries.filter(gallery__in=self.fields['galleries'].queryset).exclude(gallery__in=selected).delete()
        for gallery in selected:
            GalleryEntry.objects.get_or_create(gallery=gallery, piece=piece, defaults={'title': piece.name})

class WorkshopResourceForm(ResourceForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].queryset = manageable_circles(self.user).select_related('parent').order_by('name')
        self.fields['group'].label_from_instance = lambda obj: obj.path
        self.fields['group'].empty_label = _('Personal')
        self.fields['group'].help_text = _('Los materiales del grupo estarán disponibles en todos sus subgrupos. Sus administradores podrán gestionarlos.')
        if self.instance.group_id:
            self.fields['group'].disabled = True

    def clean(self):
        data = super().clean()
        legacy_sharing = self.data.getlist('shared_groups') if hasattr(self.data, 'getlist') else self.data.get('shared_groups', [])
        if any(legacy_sharing):
            raise forms.ValidationError(_('Los materiales no se comparten con grupos. Guárdalos como personales o en un taller que administres.'))
        return data

class MoldForm(WorkshopResourceForm):
    photos = PhotosField(label=_('Fotos del molde'))
    class Meta:
        model = Mold
        fields = ['name','group','kind','material','dimensions','parts','location','state','notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance._state.adding:
            self.initial.setdefault('kind', _('Presión'))
            self.initial.setdefault('material', _('Escayola'))
        self.fields['name'].widget.attrs.update(placeholder=_('Por ejemplo, cuenco mediano'), autofocus=True)
        self.fields['kind'].widget.attrs.update(placeholder=_('Presión, colada…'), list='mold-kinds')
        self.fields['material'].widget.attrs.update(placeholder=_('Escayola, silicona…'), list='mold-materials')
        self.fields['location'].widget.attrs['placeholder'] = _('Por ejemplo, estantería A · balda 2')
        self.fields['dimensions'].widget.attrs['placeholder'] = _('Por ejemplo, Ø 18 × 7 cm')
        self.fields['notes'].widget.attrs.update(placeholder=_('Tiempos de colada, desmoldeo, cuidados…'), rows=3)

class GlazeForm(WorkshopResourceForm):
    TYPE_FIELDS = {
        'glaze': ('finish', 'transparency', 'application'),
        'engobe': ('application_stage', 'compatible_clays', 'application'),
        'clay': ('clay_body', 'grog_percentage', 'grog_size', 'shrinkage', 'absorption', 'measurement_temperature', 'working_methods'),
    }
    photos = PhotosField(label=_('Fotografías del material'))
    class Meta:
        model = Glaze
        fields = ['name','group','material_type','kind','brand','color','temperature',
                  'finish','transparency','application','application_stage','compatible_clays',
                  'clay_body','grog_percentage','grog_size','shrinkage','absorption',
                  'measurement_temperature','working_methods','notes']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Older open forms do not submit the newly introduced category.
        self.fields['material_type'].required = False
        self.fields['material_type'].widget = forms.RadioSelect(choices=Glaze.MaterialType.choices)
        self.material_type = (self.data.get('material_type') if self.is_bound else self.initial.get('material_type')) or self.instance.material_type
        # Ignore fields from other categories, including malformed or forged input.
        # Their existing values survive reclassification, so history is not lost.
        active_fields = self.TYPE_FIELDS.get(self.material_type, ())
        for name in set(sum(self.TYPE_FIELDS.values(), ())):
            if name not in active_fields:
                self.fields[name].disabled = True
        self.fields['kind'].label = _('Procedencia')
        self.fields['kind'].widget = forms.RadioSelect(choices=self.fields['kind'].choices)
        examples = {'glaze': _('Por ejemplo, blanco avena'), 'engobe': _('Por ejemplo, engobe azul'), 'clay': _('Por ejemplo, gres blanco con chamota')}
        self.fields['name'].widget.attrs.update(placeholder=examples.get(self.material_type, examples['glaze']), autofocus=True)
        self.fields['brand'].widget.attrs['placeholder'] = _('Fabricante y código del producto')
        self.fields['finish'].widget.attrs.update(placeholder=_('Mate, satinado, brillante…'), list='glaze-finishes')
        self.fields['temperature'].widget.attrs['placeholder'] = _('Por ejemplo, 1.220–1.260 °C')
        self.fields['color'].widget.attrs['placeholder'] = _('Por ejemplo, blanco, terracota o azul cobalto')
        self.fields['application'].widget.attrs['placeholder'] = _('Pincel, inmersión, vertido o pulverización')
        self.fields['application_stage'].widget.attrs['placeholder'] = _('Húmedo, dureza de cuero, seco o bizcochado')
        self.fields['compatible_clays'].widget.attrs['placeholder'] = _('Pastas con las que has comprobado que funciona')
        self.fields['clay_body'].widget.attrs.update(placeholder=_('Gres, loza, porcelana, refractario…'), list='clay-bodies')
        self.fields['grog_size'].widget.attrs['placeholder'] = _('Por ejemplo, 0–0,5 mm')
        self.fields['working_methods'].widget.attrs['placeholder'] = _('Torno, modelado, placas o colada')
        self.fields['measurement_temperature'].help_text = _('Temperatura a la que corresponden la contracción y la absorción indicadas.')
        self.fields['notes'].widget.attrs.update(placeholder=_('Comportamiento en el taller y observaciones…'), rows=3)

    def clean_material_type(self):
        return self.cleaned_data['material_type'] or self.instance.material_type

    def clean(self):
        data = super().clean()
        if data.get('material_type') == 'clay' and any(data.get(name) is not None for name in ('shrinkage', 'absorption')) and not data.get('measurement_temperature'):
            self.add_error('measurement_temperature', _('Indica la temperatura de referencia de estas mediciones.'))
        return data

class ProgressForm(forms.ModelForm):
    photos = PhotosField(label=_('Fotos de esta etapa'))
    class Meta:
        model = Progress
        fields = ['date','stage','notes']
        widgets = {'date': DateInput(), 'notes': forms.Textarea(attrs={'rows':4})}

class SampleForm(forms.ModelForm):
    photos = PhotosField(label=_('Fotos del resultado'))
    class Meta:
        model = Sample
        fields = ['date','clay','temperature','layers','application_stage','application','shrinkage','absorption','notes']
        widgets = {'date': DateInput(), 'notes': forms.Textarea(attrs={'rows':3})}

    def __init__(self, *args, material=None, **kwargs):
        super().__init__(*args, **kwargs)
        numeric_limits(self)
        self.material = material
        category = material.material_type if material else 'glaze'
        if category == 'clay':
            for name in ('clay', 'layers', 'application_stage'):
                self.fields.pop(name)
            self.fields['application'].label = _('Conformado / atmósfera de cocción')
        else:
            self.fields['clay'].required = True
            self.fields['layers'].required = True
            for name in ('shrinkage', 'absorption'):
                self.fields.pop(name)
            if category == 'glaze':
                self.fields.pop('application_stage')

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.material and self.material.material_type == 'clay':
            obj.clay = ''
            obj.layers = None
        if commit:
            obj.save()
        return obj

class RecipeForm(forms.Form):
    ingredients = forms.CharField(label=_('Ingredientes y porcentajes'), widget=forms.Textarea(attrs={'rows':7,'placeholder':_('Feldespato; 40\nSílice; 25\nCaolín; 20\nCarbonato cálcico; 15')}), help_text=_('Un ingrediente por línea: nombre; porcentaje. El total debe sumar 100. Se guardará una nueva versión.'))
    notes = forms.CharField(label=_('Notas de esta versión'), required=False, widget=forms.Textarea(attrs={'rows':3}))

    def clean_ingredients(self):
        rows = []
        for line in self.cleaned_data['ingredients'].splitlines():
            if not line.strip():
                continue
            try:
                name, number = line.rsplit(';',1)
                value = Decimal(number.strip().replace(',','.'))
                if not name.strip() or len(name.strip()) > 120 or not value.is_finite() or not 0 < value <= 100 or value.as_tuple().exponent < -3:
                    raise ValueError
                rows.append((name.strip(), value))
            except (ValueError, InvalidOperation):
                raise forms.ValidationError(_('Usa «Nombre; porcentaje», con hasta tres decimales y valores entre 0 y 100.'))
        if not rows or len(rows) > 50 or sum(value for _unused, value in rows) != Decimal('100'):
            raise forms.ValidationError(_('La receta debe tener entre 1 y 50 ingredientes y sumar exactamente 100 %.'))
        return rows

class GlazeUseForm(forms.ModelForm):
    class Meta:
        model = GlazeUse
        fields = ['glaze','grams','layers','zone','method']

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        numeric_limits(self)
        self.fields['glaze'].queryset = available_materials(visible(Glaze.objects.all(), user))
        self.fields['glaze'].widget = MaterialSelect(choices=self.fields['glaze'].choices)
        self.fields['method'].label = _('Uso / técnica / orden')
        self.fields['glaze'].label_from_instance = material_choice_label
        if self.instance.pk and not self.fields['glaze'].queryset.filter(pk=self.instance.glaze_id).exists():
            previous_id = self.instance.glaze_id
            self.fields['glaze'].queryset = Glaze.objects.filter(Q(pk__in=self.fields['glaze'].queryset.values('pk')) | Q(pk=previous_id))
            self.fields['glaze'].label_from_instance = lambda obj: _('Material no disponible') if obj.pk==previous_id and not can_read(obj, user) else material_choice_label(obj)
        selected_id = self.data.get('glaze') if self.is_bound else self.instance.glaze_id
        try:
            selected = self.fields['glaze'].queryset.filter(pk=selected_id).first() if selected_id else None
        except (ValueError, forms.ValidationError):
            selected = None
        self.fields['layers'].widget.attrs['data-coating-layers'] = ''
        if selected and selected.material_type == 'clay':
            self.fields['layers'].disabled = True

    def save(self, commit=True):
        obj = super().save(commit=False)
        if obj.glaze.material_type == 'clay':
            obj.layers = None
        if commit:
            obj.save()
        return obj


class MaterialSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and hasattr(value, 'instance'):
            option['attrs']['data-material-type'] = value.instance.material_type
        return option

class CircleForm(forms.ModelForm):
    class Meta:
        model = Circle
        fields = ['name','description','parent']
        widgets = {'description': forms.Textarea(attrs={'rows':3})}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = manageable_circles(user).exclude(pk=self.instance.pk).select_related('parent').order_by('name')
        self.fields['parent'].label_from_instance = lambda obj: obj.path
        self.fields['parent'].empty_label = _('Taller independiente')
        if not self.instance._state.adding:
            if self.instance.parent_id and not self.fields['parent'].queryset.filter(pk=self.instance.parent_id).exists():
                self.fields['parent'].queryset = Circle.objects.filter(pk=self.instance.parent_id)
                self.fields['parent'].disabled = True
                self.fields['parent'].help_text = _('Solo la administración del grupo superior puede cambiar su ubicación.')
            else:
                descendants = {self.instance.pk}
                parents = dict(Circle.objects.values_list('pk', 'parent_id'))
                while True:
                    expanded = descendants | {pk for pk, parent in parents.items() if parent in descendants}
                    if expanded == descendants:
                        break
                    descendants = expanded
                self.fields['parent'].queryset = self.fields['parent'].queryset.exclude(pk__in=descendants)
                self.fields['parent'].help_text = _('Al cambiar el grupo superior, cambiará quién puede consultar y administrar sus contenidos.')

class GalleryForm(ResourceForm):
    class Meta:
        model = Gallery
        fields = ['name','description','workshop','audience','shared_groups']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['workshop'].queryset = sharing_circles(self.user).select_related('parent').order_by('name')
        self.fields['workshop'].empty_label = _('Mis galerías personales')
        self.fields['workshop'].help_text = _('En un taller, sus miembros pueden añadir sus propias piezas.')
        if self.instance.workshop_id:
            # Location is stable; moving a collaborative gallery needs an explicit migration.
            self.fields['workshop'].queryset = Circle.objects.filter(pk=self.instance.workshop_id)
            self.fields['workshop'].disabled = True
        self.fields['name'].widget.attrs.update(placeholder=_('Por ejemplo, pequeños rituales'), autofocus=True)
        self.fields['description'].widget.attrs.update(placeholder=_('Qué une a las piezas de esta colección…'), rows=5)

    def clean(self):
        data = super().clean()
        if data.get('workshop'):
            if data.get('audience') == 'private':
                self.add_error('audience', _('Una galería de taller debe ser visible para sus miembros o pública.'))
            data['shared_groups'] = Circle.objects.none()
        elif data.get('audience') == 'group' and not data.get('shared_groups'):
            self.add_error('shared_groups', _('Selecciona al menos un grupo.'))
        elif data.get('audience') in {'private','public'}:
            data['shared_groups'] = Circle.objects.none()
        return data

class GalleryEntryForm(forms.ModelForm):
    class Meta:
        model = GalleryEntry
        fields = ['piece','title','description','materials','dimensions','availability','photos']
        widgets = {'description': forms.Textarea(attrs={'rows':3}), 'photos': forms.CheckboxSelectMultiple()}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['piece'].queryset = Piece.objects.filter(owner=user)
        self.fields['piece'].widget = forms.HiddenInput()
        self.fields['title'].widget.attrs['placeholder'] = _('El nombre que quieres mostrar')
        self.fields['description'].widget.attrs['placeholder'] = _('Cuenta algo sobre esta pieza, sin tus notas de trabajo.')
        self.fields['availability'].widget.attrs.update(placeholder=_('Solo exposición, disponible, vendida…'), list='availability-options')
        piece_id = self.data.get('piece') or (str(self.instance.piece_id) if not self.instance._state.adding else self.initial.get('piece'))
        from .models import Photo
        # An untrusted piece id must never expose somebody else's photographs.
        try:
            self.fields['photos'].queryset = Photo.objects.filter(piece__owner=user, piece_id=piece_id) if piece_id else Photo.objects.none()
        except (ValueError, forms.ValidationError):
            self.fields['photos'].queryset = Photo.objects.none()
        from django.utils.formats import date_format
        self.fields['photos'].label_from_instance = lambda obj: obj.caption or _('Foto del %(date)s · %(id)s') % {'date': date_format(obj.created_at, 'SHORT_DATE_FORMAT'), 'id': str(obj.pk)[:6]}
        self.fields['photos'].help_text = _('Solo estas fotos serán visibles en la galería. Las notas, etapas y recetas de la pieza permanecen privadas.')

class PiecePresentationForm(forms.ModelForm):
    class Meta:
        from .models import PiecePresentation
        model = PiecePresentation
        fields = ['title', 'description', 'technique', 'materials', 'dimensions', 'availability', 'photos', 'cover']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'photos': forms.CheckboxSelectMultiple()}

    def __init__(self, *args, piece, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.piece = piece
        self.fields['photos'].queryset = piece.photos.all()
        self.fields['cover'].queryset = piece.photos.all()
        self.fields['cover'].empty_label = _('Primera foto seleccionada')
        photo_numbers = {photo.pk: number for number, photo in enumerate(piece.photos.all(), 1)}
        for name in ('photos', 'cover'):
            self.fields[name].label_from_instance = lambda photo: photo.caption or _('Foto %(number)s') % {'number': photo_numbers[photo.pk]}
        self.fields['description'].help_text = _('Solo estos textos y las fotos seleccionadas se mostrarán en las galerías y en Inspiración.')

    def clean(self):
        data = super().clean()
        photos, cover = data.get('photos'), data.get('cover')
        if cover and photos is not None and cover not in photos:
            self.add_error('cover', _('Selecciona también la foto elegida como portada.'))
        if self.instance.published and not photos:
            self.add_error('photos', _('Una pieza publicada en Inspiración necesita al menos una foto.'))
        return data


class AddMemberForm(forms.Form):
    username = forms.CharField(label=_('Usuario que quieres añadir'), max_length=150)

    def clean_username(self):
        try:
            return User.objects.get(username=self.cleaned_data['username'])
        except User.DoesNotExist:
            raise forms.ValidationError(_('No existe ninguna cuenta con ese nombre de usuario.'))
