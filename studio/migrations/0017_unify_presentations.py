from django.db import migrations


def unify(apps, schema_editor):
    Entry = apps.get_model('studio', 'GalleryEntry')
    Presentation = apps.get_model('studio', 'PiecePresentation')
    alias = schema_editor.connection.alias
    for piece_id in Entry.objects.using(alias).values_list('piece_id', flat=True).distinct():
        entries = list(Entry.objects.using(alias).filter(piece_id=piece_id).select_related('piece').order_by('pk'))
        # A common presentation must not make a private gallery's text or photos
        # visible in another gallery. Preserve divergent originals on the entries.
        values = {}
        for field in ('title', 'description', 'materials', 'dimensions', 'availability'):
            options = {entry.piece.name if field == 'title' and entry.follow_piece else getattr(entry, field) for entry in entries}
            values[field] = options.pop() if len(options) == 1 else ('Pieza' if field == 'title' else '')
        selections = [set(entry.photos.using(alias).values_list('pk', flat=True)) for entry in entries]
        shared = set.intersection(*selections)
        conflict = any(selection != selections[0] for selection in selections)
        for field in ('title', 'description', 'materials', 'dimensions', 'availability'):
            options = {entry.piece.name if field == 'title' and entry.follow_piece else getattr(entry, field) for entry in entries}
            conflict = conflict or len(options) > 1
        presentation = Presentation.objects.using(alias).create(piece_id=piece_id, needs_review=conflict, **values)
        presentation.photos.set(shared)


class Migration(migrations.Migration):
    dependencies = [('studio', '0016_piece_presentation')]
    operations = [migrations.RunPython(unify, migrations.RunPython.noop)]
