from io import BytesIO
from PIL import Image, ImageOps
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from .models import Photo


def material_has_history(material):
    from django.db.models import Q
    from .models import GlazeUse, Mold, Piece, Sample
    if isinstance(material, Mold):
        return Piece.objects.filter(mold=material).exists()
    return (Piece.objects.filter(clay_material=material).exists()
            or GlazeUse.objects.filter(Q(glaze=material) | Q(recipe_version__glaze=material)).exists()
            or Sample.objects.filter(recipe_version__glaze=material).exclude(glaze=material).exists())


@transaction.atomic
def delete_material(material):
    """Protect piece history and remove files only after committing the deletion."""
    from django.db.models import Q
    from django.db.models.deletion import ProtectedError
    from .models import Mold
    material = type(material).objects.select_for_update().get(pk=material.pk)
    if material_has_history(material):
        raise ProtectedError('Material in use', [material])
    photos = list(material.photos.all()) if isinstance(material, Mold) else list(Photo.objects.filter(Q(glaze=material) | Q(sample__glaze=material)).distinct())
    # Samples may reference this material's own protected recipe versions.
    # Delete them first, within the same transaction as the material.
    if not isinstance(material, Mold):
        material.samples.all().delete()
    material.delete()
    schedule_photo_cleanup(photos)


def schedule_photo_cleanup(photos):
    files = [(field.storage, field.name) for photo in photos
             for field in (photo.original, photo.image, photo.thumbnail) if field.name]

    def clean_files():
        import logging
        for storage, name in files:
            try:
                storage.delete(name)
            except Exception:
                logging.getLogger(__name__).exception('No se pudo retirar un archivo de una foto eliminada.')

    transaction.on_commit(clean_files)


@transaction.atomic
def delete_piece(piece):
    """Remove the record atomically; clean its files only after a successful commit."""
    photos = list(piece.photos.all())
    piece.delete()
    schedule_photo_cleanup(photos)

@transaction.atomic
def save_photos(files, *, piece=None, mold=None, glaze=None, sample=None, progress=None):
    saved = []
    parent = piece or mold or glaze or sample
    if not parent:
        raise ValueError('La fotografía necesita un recurso.')
    type(parent).objects.select_for_update().get(pk=parent.pk)
    last = parent.photos.aggregate(last=Max('position'))['last']
    position = last + 1 if last is not None else 0
    for upload in files:
        photo = Photo(piece=piece, mold=mold, glaze=glaze, sample=sample, progress=progress, position=position)
        raw = upload.read()
        source = Image.open(BytesIO(raw))
        extension = {'JPEG':'jpg', 'PNG':'png', 'WEBP':'webp'}[source.format]
        photo.original.save('original.'+extension, ContentFile(raw), save=False)
        oriented = ImageOps.exif_transpose(source)
        image = Image.new('RGB', oriented.size, '#fffdf9')
        if oriented.mode in ('RGBA','LA') or 'transparency' in oriented.info:
            rgba = oriented.convert('RGBA')
            image.paste(rgba, mask=rgba.getchannel('A'))
        else:
            image.paste(oriented.convert('RGB'))
        image.thumbnail((1800,1800))
        output = BytesIO()
        image.save(output, 'JPEG', quality=87, optimize=True)
        photo.image.save('image.jpg', ContentFile(output.getvalue()), save=False)
        image.thumbnail((650,650))
        output = BytesIO()
        image.save(output, 'JPEG', quality=82, optimize=True)
        photo.thumbnail.save('thumb.jpg', ContentFile(output.getvalue()), save=False)
        photo.save()
        saved.append(photo)
        position += 1
    return saved
