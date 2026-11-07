from django.db import migrations, models
import django.db.models.deletion


def link_existing_clay_uses(apps, schema_editor):
    Piece = apps.get_model('studio', 'Piece')
    GlazeUse = apps.get_model('studio', 'GlazeUse')
    alias = schema_editor.connection.alias
    for piece in Piece.objects.using(alias).exclude(clay='').iterator():
        clays = list(GlazeUse.objects.using(alias).filter(piece_id=piece.pk,
            glaze__material_type='clay').values_list('glaze_id', 'glaze__name').distinct()[:2])
        if len(clays) == 1 and clays[0][1].strip().casefold() == piece.clay.strip().casefold():
            Piece.objects.using(alias).filter(pk=piece.pk).update(clay_material_id=clays[0][0])


class Migration(migrations.Migration):
    dependencies = [('studio', '0011_gallery_workshop')]
    operations = [
        migrations.AddField(model_name='piece', name='clay_material', field=models.ForeignKey(
            blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
            related_name='clay_pieces', to='studio.glaze', verbose_name='Barro / pasta')),
        migrations.RunPython(link_existing_clay_uses, migrations.RunPython.noop),
    ]
