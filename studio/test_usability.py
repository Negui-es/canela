from html.parser import HTMLParser

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .models import Gallery, GalleryEntry, Glaze, Piece, PiecePresentation, User


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


@override_settings(SECURE_SSL_REDIRECT=False, LANGUAGE_CODE='es')
class UsabilityTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.owner = User.objects.create_user('usability-owner', email='owner@example.test')
        self.piece = Piece.objects.create(owner=self.owner, name='Cuenco')
        self.material = Glaze.objects.create(owner=self.owner, name='Avena', kind='recipe')
        self.client.force_login(self.owner)

    def test_recipe_and_sample_cancel_return_to_the_material(self):
        back = reverse('glaze', args=[self.material.pk])
        for route in ('recipe_add', 'sample_add', 'glaze_edit'):
            response = self.client.get(reverse(route, args=[self.material.pk]))
            self.assertEqual(response.context['back_url'], back)
            self.assertContains(response, 'href="' + back + '"')
        response = self.client.get(reverse('password_change'))
        self.assertContains(response, 'href="' + reverse('account') + '"')

    def test_piece_editor_keeps_the_original_as_the_cancel_destination(self):
        response = self.client.get(reverse('piece_edit', args=[self.piece.pk]))
        self.assertContains(response, 'href="' + reverse('piece', args=[self.piece.pk]) + '"')

    def test_error_summary_has_working_field_targets_and_description_ids(self):
        response = self.client.post(reverse('piece_new'), {'name': '', 'started_on': 'bad-date', 'stage': 'raw', 'tag_names': 'a' * 41})
        html = response.content.decode()
        document = Document(html)
        ids = {attrs['id'] for _, attrs in document.elements if 'id' in attrs}
        self.assertContains(response, 'data-form-errors')
        self.assertContains(response, 'data-error-target="id_name"')
        for _, attrs in document.elements:
            if 'data-error-target' in attrs:
                self.assertIn(attrs['data-error-target'], ids)
            for identifier in attrs.get('aria-describedby', '').split():
                self.assertIn(identifier, ids)

    def test_recipe_keeps_native_submission_and_server_total_validation(self):
        url = reverse('recipe_add', args=[self.material.pk])
        self.assertContains(self.client.get(url), 'data-recipe-editor')
        invalid = self.client.post(url, {'ingredients': 'Sílice; 60\nCaolín; 30'})
        self.assertContains(invalid, 'data-form-errors')
        self.assertFalse(self.material.versions.exists())
        response = self.client.post(url, {'ingredients': 'Sílice; 66.667\nCaolín; 33.333', 'notes': 'Prueba'})
        self.assertRedirects(response, reverse('glaze', args=[self.material.pk]))
        self.assertEqual(self.material.versions.get().ingredients.count(), 2)

    def test_editing_an_existing_gallery_presentation_does_not_say_add(self):
        gallery = Gallery.objects.create(owner=self.owner, name='Colección')
        entry = GalleryEntry.objects.create(gallery=gallery, piece=self.piece, title='Cuenco')
        PiecePresentation.objects.create(piece=self.piece, title='Cuenco')
        response = self.client.get(reverse('gallery_entry_edit', args=[gallery.pk, entry.pk]))
        self.assertContains(response, 'Guardar presentación')
        self.assertNotContains(response, 'Guardar y añadir a la galería')

    def test_workshops_are_available_from_desktop_navigation(self):
        response = self.client.get(reverse('dashboard'))
        nav = response.content.decode().split('class="space-navigation"', 1)[1].split('</nav>', 1)[0]
        self.assertIn('href="' + reverse('workshops') + '"', nav)

    def test_form_help_is_available_for_profile_and_password_fields(self):
        for route in ('account', 'password_change'):
            response = self.client.get(reverse(route))
            document = Document(response.content.decode())
            ids = {attrs['id'] for _, attrs in document.elements if 'id' in attrs}
            for _, attrs in document.elements:
                for identifier in attrs.get('aria-describedby', '').split():
                    self.assertIn(identifier, ids)

    def test_numeric_model_limits_are_present_in_the_browser_controls(self):
        from .forms import PieceForm, GlazeForm, GlazeUseForm, SampleForm
        self.assertEqual(PieceForm(user=self.owner).fields['weight'].widget.attrs['min'], '0')
        clay = GlazeForm(user=self.owner)
        self.assertEqual(clay.fields['grog_percentage'].widget.attrs['max'], '100')
        sample = SampleForm(material=self.material)
        self.assertEqual(sample.fields['temperature'].widget.attrs['max'], '1800')
        self.assertEqual(GlazeUseForm(user=self.owner).fields['layers'].widget.attrs['min'], '1')
