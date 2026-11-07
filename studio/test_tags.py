from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from .forms import PieceForm
from .models import Circle, Piece, Tag, User


@override_settings(LANGUAGE_CODE='es')
class PieceTagTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.owner = User.objects.create_user('tag-owner')
        self.other = User.objects.create_user('tag-other')
        self.client.force_login(self.owner)

    def create_piece(self, tags, name='Pieza etiquetada'):
        response = self.client.post(reverse('piece_new'), {
            'name': name, 'stage': 'raw', 'started_on': '2026-10-27',
            'tags_present': '1', 'tag_names': tags,
        })
        self.assertEqual(response.status_code, 302)
        return Piece.objects.get(name=name)

    def test_tags_normalize_and_deduplicate_and_display(self):
        piece = self.create_piece(' Plato , vajilla; PLATO,  edición   azul , edición azul')
        self.assertEqual(list(piece.tags.values_list('name', flat=True)), ['edición azul', 'plato', 'vajilla'])
        form = PieceForm(user=self.owner, instance=piece)
        self.assertEqual(form.initial['tag_names'], 'edición azul, plato, vajilla')
        detail = self.client.get(reverse('piece', args=[piece.pk]))
        self.assertContains(detail, '?scope=shared&amp;tag=plato')
        self.assertContains(self.client.get(reverse('pieces')), 'tag-pill')

    def test_editing_and_clearing_tags_does_not_change_other_pieces(self):
        first = self.create_piece('plato, vajilla', name='Primera')
        second = self.create_piece('plato', name='Segunda')
        payload = {'name': first.name, 'stage': first.stage, 'started_on': '2026-10-27', 'tags_present': '1', 'tag_names': 'regalo'}
        self.assertEqual(self.client.post(reverse('piece_edit', args=[first.pk]), payload).status_code, 302)
        self.assertEqual(list(first.tags.values_list('name', flat=True)), ['regalo'])
        self.assertEqual(list(second.tags.values_list('name', flat=True)), ['plato'])
        payload['tag_names'] = ''
        self.assertEqual(self.client.post(reverse('piece_edit', args=[first.pk]), payload).status_code, 302)
        self.assertFalse(first.tags.exists())

    def test_old_open_forms_preserve_tags(self):
        piece = self.create_piece('vajilla')
        response = self.client.post(reverse('piece_edit', args=[piece.pk]), {'name': piece.name, 'stage': 'finished', 'started_on': '2026-10-27'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(piece.tags.filter(name='vajilla').exists())

    def test_tag_filter_is_exact_and_combines_with_stage_and_search(self):
        matching = self.create_piece('plato, vajilla', name='Azul')
        self.create_piece('plato hondo', name='Otro azul')
        finished = self.create_piece('plato', name='Azul terminado')
        finished.stage = 'finished'; finished.save()
        response = self.client.get(reverse('pieces'), {'tag': ' PLATO ', 'q': 'Azul', 'stage': 'raw'})
        self.assertEqual(list(response.context['pieces']), [matching])
        self.assertContains(response, '<option value="plato" selected>')
        self.assertNotContains(response, 'Otro azul')
        self.assertEqual(self.client.get(reverse('pieces'), {'tag': 'ausente'}).context['page'].paginator.count, 0)

    def test_text_search_matches_tags_without_duplicate_results(self):
        piece = self.create_piece('plato, plato hondo', name='Sin término en nombre')
        response = self.client.get(reverse('pieces'), {'q': 'PLATO'})
        self.assertEqual(list(response.context['pieces']), [piece])
        Piece.objects.create(owner=self.owner, name='Sin-etiquetas')
        self.assertEqual(self.client.get(reverse('pieces'), {'q': '   '}).context['page'].paginator.count, 2)

    def test_suggestions_and_filters_only_expose_visible_pieces(self):
        root = Circle.objects.create(owner=self.other, name='Taller')
        child = Circle.objects.create(owner=self.other, name='Clase', parent=root)
        child.members.add(self.owner)
        shared = Piece.objects.create(owner=self.other, name='Compartida')
        shared.shared_groups.add(root)
        shared.tags.add(Tag.objects.create(name='general-visible'))
        private = Piece.objects.create(owner=self.other, name='Privada')
        private.tags.add(Tag.objects.create(name='etiqueta-secreta'))
        response = self.client.get(reverse('pieces'), {'scope': 'shared', 'tag': 'general-visible'}, HTTP_HX_REQUEST='true')
        self.assertEqual(list(response.context['pieces']), [shared])
        self.assertContains(response, 'hx-swap-oob="outerHTML"')
        self.assertNotContains(response, 'etiqueta-secreta')
        suggestions = self.client.get(reverse('piece_new'))
        self.assertContains(suggestions, 'general-visible')
        self.assertNotContains(suggestions, 'etiqueta-secreta')
        child.members.remove(self.owner)
        self.assertNotContains(self.client.get(reverse('piece_new')), 'general-visible')
        self.assertEqual(self.client.get(reverse('pieces'), {'scope': 'shared', 'tag': 'general-visible'}).context['page'].paginator.count, 0)

    def test_pagination_preserves_tag_and_other_filters(self):
        tag = Tag.objects.create(name='vajilla')
        for index in range(19):
            Piece.objects.create(owner=self.owner, name=f'Pieza {index}', stage='raw').tags.add(tag)
        response = self.client.get(reverse('pieces'), {'tag': 'vajilla', 'stage': 'raw', 'scope': 'shared'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.context['page'].paginator.count, 19)
        for value in ['tag=vajilla', 'stage=raw', 'scope=shared', 'page=2']:
            self.assertContains(response, value)

    def test_invalid_tags_do_not_save_piece(self):
        for value in ['a' * 41, ','.join(str(number) for number in range(21))]:
            response = self.client.post(reverse('piece_new'), {'name': 'Inválida', 'stage': 'raw', 'started_on': '2026-10-27', 'tag_names': value})
            self.assertIn('tag_names', response.context['form'].errors)
            self.assertFalse(Piece.objects.filter(name='Inválida').exists())

    def test_other_users_cannot_change_tags(self):
        piece = self.create_piece('plato')
        self.client.force_login(self.other)
        response = self.client.post(reverse('piece_edit', args=[piece.pk]), {'name': piece.name, 'stage': 'raw', 'started_on': '2026-10-27', 'tag_names': 'cambiada'})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(list(piece.tags.values_list('name', flat=True)), ['plato'])
