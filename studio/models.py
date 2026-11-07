from django.utils.translation import gettext_lazy as _
import uuid
from decimal import Decimal
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone

class User(AbstractUser):
    display_name = models.CharField(_('Nombre'), max_length=80, blank=True)
    bio = models.TextField(_('Sobre mí'), blank=True)

    class Meta(AbstractUser.Meta):
        constraints = [models.UniqueConstraint(
            Lower(Trim('email')), condition=~Q(email=''), name='unique_account_email',
        )]

    @property
    def name(self):
        return self.display_name or self.username

class Circle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_circles')
    name = models.CharField(_('Nombre'), max_length=100)
    description = models.TextField(_('Descripción'), blank=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='circles', blank=True)
    administrators = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='administered_circles', blank=True)
    parent = models.ForeignKey('self', verbose_name=_('Dentro de'), null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def path(self):
        names, seen, current = [], set(), self
        while current and current.pk not in seen:
            seen.add(current.pk)
            names.append(current.name)
            current = current.parent
        return ' / '.join(reversed(names))

    def clean(self):
        super().clean()
        seen = {self.pk}
        current = self.parent if self.parent_id else None
        while current:
            if current.pk in seen:
                raise ValidationError({'parent': _('Un grupo no puede estar dentro de sí mismo ni de uno de sus subgrupos.')})
            seen.add(current.pk)
            current = current.parent

class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    circle = models.ForeignKey(Circle, null=True, blank=True, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    used_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    used_at = models.DateTimeField(null=True, blank=True)

    @property
    def available(self):
        return self.used_at is None and self.expires_at > timezone.now()

class Resource(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='%(class)ss')
    name = models.CharField(_('Nombre'), max_length=120)
    notes = models.TextField(_('Notas de taller'), blank=True)
    shared_groups = models.ManyToManyField(Circle, blank=True, related_name='%(class)ss', verbose_name=_('Compartir con grupos'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-updated_at']

    def __str__(self):
        return self.name

    @property
    def reference(self):
        return str(self.pk)[:8].upper()

class MaterialAvailability(models.TextChoices):
    AVAILABLE = 'available', _('Disponible')
    OUT_OF_STOCK = 'out_of_stock', _('Agotado')
    RETIRED = 'retired', _('Retirado')
    UNAVAILABLE = 'unavailable', _('No disponible')


class Mold(Resource):
    availability = models.CharField(_('Disponibilidad'), max_length=20, choices=MaterialAvailability, default=MaterialAvailability.AVAILABLE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='molds')
    group = models.ForeignKey(Circle, verbose_name=_('Guardar en'), null=True, blank=True, on_delete=models.PROTECT, related_name='workshop_molds')
    kind = models.CharField(_('Tipo'), max_length=60, default='Presión')
    material = models.CharField(_('Material'), max_length=80, default='Escayola')
    dimensions = models.CharField(_('Dimensiones'), max_length=120, blank=True)
    parts = models.PositiveSmallIntegerField(_('Número de partes'), default=1, validators=[MinValueValidator(1)])
    location = models.CharField(_('Ubicación'), max_length=120, blank=True)
    state = models.CharField(_('Estado del molde'), max_length=20, choices=[('available',_('Buen estado')),('in_use',_('En uso')),('drying',_('Secando')),('damaged',_('Deteriorado'))], default='available')

    @property
    def is_retired(self):
        return self.availability == MaterialAvailability.RETIRED

    @property
    def is_available(self):
        return self.availability == MaterialAvailability.AVAILABLE

class Glaze(Resource):
    availability = models.CharField(_('Disponibilidad'), max_length=20, choices=MaterialAvailability, default=MaterialAvailability.AVAILABLE)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='glazes')
    group = models.ForeignKey(Circle, verbose_name=_('Guardar en'), null=True, blank=True, on_delete=models.PROTECT, related_name='materials')
    class MaterialType(models.TextChoices):
        GLAZE = 'glaze', _('Esmalte')
        ENGOBE = 'engobe', _('Engobe')
        CLAY = 'clay', _('Barro')

    material_type = models.CharField(_('Tipo de material'), max_length=20, choices=MaterialType, default=MaterialType.GLAZE)
    kind = models.CharField(_('Tipo'), max_length=20, choices=[('recipe',_('Receta propia')),('commercial',_('Comercial'))], default='recipe')
    brand = models.CharField(_('Marca / referencia'), max_length=120, blank=True)
    finish = models.CharField(_('Acabado'), max_length=80, blank=True)
    temperature = models.CharField(_('Rango de temperatura'), max_length=80, blank=True)
    color = models.CharField(_('Color tras cocción'), max_length=120, blank=True)
    transparency = models.CharField(_('Transparencia'), max_length=20, blank=True, choices=[('opaque', _('Opaco')), ('translucent', _('Translúcido')), ('transparent', _('Transparente'))])
    application = models.CharField(_('Método de aplicación'), max_length=200, blank=True)
    application_stage = models.CharField(_('Estado de la pieza al aplicar'), max_length=120, blank=True)
    compatible_clays = models.CharField(_('Pastas compatibles'), max_length=200, blank=True)
    clay_body = models.CharField(_('Tipo de pasta'), max_length=80, blank=True)
    grog_percentage = models.DecimalField(_('Chamota (%)'), max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    grog_size = models.CharField(_('Grano de la chamota (mm)'), max_length=80, blank=True)
    shrinkage = models.DecimalField(_('Contracción total (%)'), max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    absorption = models.DecimalField(_('Absorción de agua (%)'), max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    measurement_temperature = models.PositiveSmallIntegerField(_('Temperatura de referencia (°C)'), null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(1800)])
    working_methods = models.CharField(_('Técnicas de conformado'), max_length=200, blank=True)

    @property
    def latest_recipe(self):
        return self.versions.order_by('-number').first()

    @property
    def is_retired(self):
        return self.availability == MaterialAvailability.RETIRED

    @property
    def is_available(self):
        return self.availability == MaterialAvailability.AVAILABLE

class RecipeVersion(models.Model):
    glaze = models.ForeignKey(Glaze, on_delete=models.CASCADE, related_name='versions')
    number = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['glaze','number'], name='unique_glaze_version')]

    def __str__(self):
        return f'{self.glaze.name} · v{self.number}'

class Ingredient(models.Model):
    version = models.ForeignKey(RecipeVersion, on_delete=models.CASCADE, related_name='ingredients')
    name = models.CharField(max_length=120)
    percentage = models.DecimalField(max_digits=6, decimal_places=3, validators=[MinValueValidator(Decimal('0.001')), MaxValueValidator(100)])

class Tag(models.Model):
    name = models.CharField(_('Etiqueta'), max_length=40, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Piece(Resource):
    class Stage(models.TextChoices):
        PROCESS = 'process', _('En proceso')
        RAW = 'raw', _('En crudo')
        BISQUE = 'bisque', _('Bizcochada')
        GLAZED = 'glazed', _('Esmaltada')
        FINISHED = 'finished', _('Terminada')
    stage = models.CharField(_('Etapa'), max_length=20, choices=Stage, default=Stage.PROCESS)
    started_on = models.DateField(_('Fecha de inicio'), default=timezone.localdate)
    clay = models.CharField(_('Barro / pasta'), max_length=120, blank=True)
    clay_material = models.ForeignKey(Glaze, verbose_name=_('Barro / pasta'), null=True, blank=True,
                                     on_delete=models.PROTECT, related_name='clay_pieces')
    technique = models.CharField(_('Técnica'), max_length=120, blank=True)
    dimensions = models.CharField(_('Dimensiones'), max_length=120, blank=True)
    weight = models.DecimalField(_('Peso (g)'), max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    mold = models.ForeignKey(Mold, verbose_name=_('Molde'), null=True, blank=True, on_delete=models.PROTECT, related_name='pieces')
    destination = models.CharField(_('Destino'), max_length=120, blank=True)
    tags = models.ManyToManyField(Tag, verbose_name=_('Etiquetas'), blank=True, related_name='pieces')

    @property
    def cover(self):
        return next(iter(self.photos.all()), None)

class Progress(models.Model):
    piece = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name='progress')
    date = models.DateField(_('Fecha'), default=timezone.localdate)
    stage = models.CharField(_('Etapa'), max_length=20, choices=Piece.Stage)
    notes = models.TextField(_('Qué has hecho o descubierto'), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date','-created_at']

class GlazeUse(models.Model):
    piece = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name='glaze_uses')
    glaze = models.ForeignKey(Glaze, verbose_name=_('Material'), on_delete=models.PROTECT)
    recipe_version = models.ForeignKey(RecipeVersion, null=True, blank=True, on_delete=models.PROTECT)
    grams = models.DecimalField(_('Cantidad (g)'), max_digits=9, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    layers = models.PositiveSmallIntegerField(_('Capas'), null=True, blank=True, validators=[MinValueValidator(1)])
    zone = models.CharField(_('Zona de la pieza'), max_length=100, blank=True)
    method = models.CharField(_('Aplicación y orden'), max_length=200, blank=True)

class Sample(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    glaze = models.ForeignKey(Glaze, on_delete=models.CASCADE, related_name='samples')
    recipe_version = models.ForeignKey(RecipeVersion, null=True, blank=True, on_delete=models.PROTECT)
    date = models.DateField(_('Fecha'), default=timezone.localdate)
    clay = models.CharField(_('Barro'), max_length=120, blank=True)
    temperature = models.PositiveSmallIntegerField(_('Temperatura (°C)'), validators=[MinValueValidator(1),MaxValueValidator(1800)])
    layers = models.PositiveSmallIntegerField(_('Capas'), null=True, blank=True, default=1, validators=[MinValueValidator(1)])
    application_stage = models.CharField(_('Estado de la pieza al aplicar'), max_length=120, blank=True)
    shrinkage = models.DecimalField(_('Contracción total (%)'), max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    absorption = models.DecimalField(_('Absorción de agua (%)'), max_digits=5, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(100)])
    application = models.CharField(_('Aplicación / atmósfera'), max_length=200, blank=True)
    notes = models.TextField(_('Resultado y observaciones'), blank=True)

def upload_path(instance, filename):
    return f'{instance.id}/{filename}'

class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    piece = models.ForeignKey(Piece, null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    mold = models.ForeignKey(Mold, null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    glaze = models.ForeignKey(Glaze, null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    sample = models.ForeignKey(Sample, null=True, blank=True, on_delete=models.CASCADE, related_name='photos')
    progress = models.ForeignKey(Progress, null=True, blank=True, on_delete=models.SET_NULL, related_name='photos')
    original = models.FileField(upload_to=upload_path)
    image = models.FileField(upload_to=upload_path)
    thumbnail = models.FileField(upload_to=upload_path)
    caption = models.CharField(max_length=200, blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', '-created_at', 'id']
        constraints = [models.CheckConstraint(condition=(
            Q(piece__isnull=False,mold__isnull=True,glaze__isnull=True,sample__isnull=True)
            | Q(piece__isnull=True,mold__isnull=False,glaze__isnull=True,sample__isnull=True)
            | Q(piece__isnull=True,mold__isnull=True,glaze__isnull=False,sample__isnull=True)
            | Q(piece__isnull=True,mold__isnull=True,glaze__isnull=True,sample__isnull=False)
        ), name='photo_one_parent')]

class Gallery(Resource):
    workshop = models.ForeignKey(Circle, verbose_name=_('Taller'), null=True, blank=True,
                                 on_delete=models.PROTECT, related_name='galleries')
    description = models.TextField(_('Presentación pública'), blank=True)
    audience = models.CharField(_('Visibilidad'), max_length=20, choices=[('private',_('Privada')),('group',_('Grupos seleccionados')),('public',_('Pública'))], default='private')

class PiecePresentation(models.Model):
    piece = models.OneToOneField(Piece, on_delete=models.CASCADE, related_name='presentation')
    title = models.CharField(_('Título público'), max_length=120)
    description = models.TextField(_('Descripción pública'), blank=True)
    technique = models.CharField(_('Técnica'), max_length=120, blank=True)
    materials = models.CharField(_('Materiales que quieres mostrar'), max_length=200, blank=True)
    dimensions = models.CharField(_('Dimensiones que quieres mostrar'), max_length=120, blank=True)
    availability = models.CharField(_('Disponibilidad'), max_length=80, blank=True)
    photos = models.ManyToManyField(Photo, blank=True, related_name='presentations')
    cover = models.ForeignKey(Photo, null=True, blank=True, on_delete=models.SET_NULL, related_name='+', verbose_name=_('Portada'))
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    needs_review = models.BooleanField(default=False)

    @property
    def display_title(self):
        return self.title

    @property
    def display_photos(self):
        photos = list(self.photos.all())
        return sorted(photos, key=lambda photo: photo.pk != self.cover_id)


class GalleryEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gallery = models.ForeignKey(Gallery, on_delete=models.CASCADE, related_name='entries')
    piece = models.ForeignKey(Piece, on_delete=models.CASCADE, related_name='gallery_entries')
    title = models.CharField(_('Título público'), max_length=120)
    description = models.TextField(_('Descripción pública'), blank=True)
    materials = models.CharField(_('Materiales que quieres mostrar'), max_length=200, blank=True)
    dimensions = models.CharField(_('Dimensiones que quieres mostrar'), max_length=120, blank=True)
    availability = models.CharField(_('Disponibilidad'), max_length=80, blank=True)
    photos = models.ManyToManyField(Photo, blank=True, related_name='gallery_entries')
    follow_piece = models.BooleanField(default=False)

    @property
    def public_presentation(self):
        # Legacy fields remain as an archive; migrated and new entries use the
        # single presentation. The fallback also supports old import scripts.
        return getattr(self.piece, 'presentation', None) or self

    @property
    def display_title(self):
        return self.piece.name if self.follow_piece else self.title

    class Meta:
        constraints = [models.UniqueConstraint(fields=['gallery','piece'], name='unique_gallery_piece')]

class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    failures = models.PositiveIntegerField(default=0)
    first_failure = models.DateTimeField(default=timezone.now)
