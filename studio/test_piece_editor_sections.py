from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .forms import PieceForm
from .models import Circle, Gallery, GalleryEntry, Glaze, GlazeUse, Piece, User


@override_settings(SECURE_SSL_REDIRECT=False)
class PieceEditorSectionsTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.user = User.objects.create_user('editor-sections')
        self.client.force_login(self.user)
        self.clay = Glaze.objects.create(owner=self.user, name='Gres', material_type='clay')
        self.glaze = Glaze.objects.create(owner=self.user, name='Avena', material_type='glaze')
        self.engobe = Glaze.objects.create(owner=self.user, name='Azul', material_type='engobe')
        self.personal = Gallery.objects.create(owner=self.user, name='Colección')
        parent = Circle.objects.create(owner=self.user, name='Serendipia')
        child = Circle.objects.create(owner=self.user, parent=parent, name='Martes')
        self.workshop_gallery = Gallery.objects.create(owner=self.user, workshop=child, name='Colección')

    def test_material_choices_are_separated_and_gallery_origins_distinguish_equal_names(self):
        form = PieceForm(user=self.user)
        groups = form.coating_sections
        self.assertEqual([group['type'] for group in groups], ['glaze', 'engobe'])
        self.assertEqual([choice.data['value'].instance for choice in groups[0]['choices']], [self.glaze])
        self.assertEqual([choice.data['value'].instance for choice in groups[1]['choices']], [self.engobe])
        self.assertEqual(form.additional_clay_choices, [])
        labels = [label for value, label in form.fields['galleries'].choices]
        self.assertIn('Colección · Personal', labels)
        self.assertIn('Colección · Serendipia / Martes', labels)

    def test_invalid_submission_preserves_gallery_selection_and_separate_materials(self):
        response = self.client.post(reverse('piece_new'), {
            'name': '', 'started_on': '2026-10-27', 'stage': 'raw',
            'clay_material': self.clay.pk, 'glazes': [self.glaze.pk, self.engobe.pk],
            'galleries': [self.personal.pk, self.workshop_gallery.pk],
        })
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(set(form['galleries'].value()), {str(self.personal.pk), str(self.workshop_gallery.pk)})
        for group in form.coating_sections:
            self.assertTrue(group['choices'][0].data['selected'])
        self.assertContains(response, 'data-gallery-picker')
        self.assertContains(response, 'multiple')
        self.assertNotContains(response, 'name="galleries" type="checkbox"')
        self.assertFalse(Piece.objects.exists())

    def test_edit_preserves_secondary_clay_and_removes_only_unselected_gallery(self):
        piece = Piece.objects.create(owner=self.user, name='Taza', clay_material=self.clay)
        GlazeUse.objects.create(piece=piece, glaze=self.clay, layers=3)
        for gallery in [self.personal, self.workshop_gallery]:
            GalleryEntry.objects.create(gallery=gallery, piece=piece, title=piece.name)
        form = PieceForm(user=self.user, instance=piece)
        self.assertEqual(len(form.additional_clay_choices), 1)
        response = self.client.post(reverse('piece_edit', args=[piece.pk]), {
            'name': piece.name, 'started_on': '2026-10-27', 'stage': 'raw',
            'clay_material': self.clay.pk, 'glazes_present': '1', 'glazes': [self.clay.pk, self.engobe.pk],
            'galleries_present': '1', 'galleries': [self.workshop_gallery.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(piece.gallery_entries.values_list('gallery_id', flat=True)), [self.workshop_gallery.pk])
        self.assertEqual(piece.glaze_uses.get(glaze=self.clay).layers, 3)
        self.assertTrue(piece.glaze_uses.filter(glaze=self.engobe).exists())
