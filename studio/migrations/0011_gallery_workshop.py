from django.db import migrations, models
import django.db.models.deletion


def assign_existing_galleries(apps, schema_editor):
    """Preserve IDs, selected photos and visibility; leave multi-group cases intact."""
    Gallery = apps.get_model('studio', 'Gallery')
    for gallery in Gallery.objects.using(schema_editor.connection.alias).filter(audience='group'):
        groups = list(gallery.shared_groups.values_list('pk', flat=True)[:2])
        if len(groups) == 1:
            Gallery.objects.using(schema_editor.connection.alias).filter(pk=gallery.pk).update(workshop_id=groups[0])


class Migration(migrations.Migration):
    dependencies = [('studio', '0010_tag_piece_tags')]
    operations = [
        migrations.AddField(model_name='gallery', name='workshop', field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='galleries', to='studio.circle', verbose_name='Taller')),
        migrations.AddField(model_name='galleryentry', name='follow_piece', field=models.BooleanField(default=False)),
        migrations.RunPython(assign_existing_galleries, migrations.RunPython.noop),
    ]
