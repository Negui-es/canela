"""Workspace boundaries, collaborative galleries and shared piece identity."""
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.apps import apps
from django.conf import settings
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .models import Circle, Gallery, GalleryEntry, Glaze, GlazeUse, Piece, User
from .permissions import can_read
from .services import save_photos
from .tests import image_file


@override_settings(LANGUAGE_CODE='es', SECURE_SSL_REDIRECT=False)
class WorkspaceTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        temporary = TemporaryDirectory(dir=settings.BASE_DIR / 'data')
        self.addCleanup(temporary.cleanup)
        storage = override_settings(MEDIA_ROOT=temporary.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.owner = User.objects.create_user('taller-admin')
        self.member = User.objects.create_user('taller-member')
        self.outsider = User.objects.create_user('taller-outsider')
        self.workshop = Circle.objects.create(owner=self.owner, name='Serendipia')
        self.workshop.members.add(self.owner, self.member)
        self.workshop.administrators.add(self.owner)
        self.other = Circle.objects.create(owner=self.outsider, name='Otro taller')
        self.other.members.add(self.outsider)
        self.gallery = Gallery.objects.create(owner=self.owner, workshop=self.workshop, name='Otoño', audience='group')
        self.personal_gallery = Gallery.objects.create(owner=self.member, name='Mis pruebas')
        self.piece = Piece.objects.create(owner=self.member, name='Taza propia', notes='NOTA PRIVADA DEL AUTOR')
        self.foreign_piece = Piece.objects.create(owner=self.owner, name='Pieza de otra persona')
        self.material = Glaze.objects.create(owner=self.member, name='ESMALTE SECRETO', notes='RECETA SECRETA')
        self.shared_material = Glaze.objects.create(owner=self.owner, group=self.workshop, name='Gres del taller')
        GlazeUse.objects.create(piece=self.piece, glaze=self.material)
        GlazeUse.objects.create(piece=self.piece, glaze=self.shared_material)
        self.client.force_login(self.member)

    def test_menu_zero_one_many_workshops(self):
        self.client.force_login(self.outsider)
        # Outsider has one workshop, while an unrelated new account has none.
        alone = User.objects.create_user('sin-taller')
        self.client.force_login(alone)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'data-workshop-select')
        self.assertNotContains(response, 'Serendipia')
        self.client.force_login(self.member)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'Serendipia')
        self.assertNotContains(response, 'data-workshop-select')
        self.other.members.add(self.member)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, 'data-workshop-select')
        self.assertNotContains(response, 'Otro taller')
        galleries = self.client.get(reverse('galleries'))
        self.assertContains(galleries, 'Serendipia')
        self.assertNotContains(galleries, 'Otro taller')

    def test_own_lists_do_not_mix_workshop_catalogs_and_other_authors(self):
        GalleryEntry.objects.create(gallery=self.gallery, piece=self.piece, title='Taza')
        self.assertContains(self.client.get(reverse('pieces')), self.piece.name)
        self.assertNotContains(self.client.get(reverse('pieces')), self.foreign_piece.name)
        self.assertContains(self.client.get(reverse('glazes')), self.material.name)
        self.assertContains(self.client.get(reverse('glazes')), self.shared_material.name)
        response = self.client.get(reverse('galleries'))
        self.assertContains(response, self.personal_gallery.name)
        self.assertIn(self.gallery, response.context['galleries'])
        self.assertEqual(set(response.context['galleries']), {self.personal_gallery, self.gallery})
        self.assertIn(self.gallery, response.context['galleries'])
        self.assertRedirects(self.client.get(reverse('workshop_galleries', args=[self.workshop.pk])), reverse('galleries'))

    def test_workshop_cannot_be_selected_by_forging_its_url(self):
        for name in ['workshop', 'workshop_galleries', 'workshop_materials']:
            self.assertEqual(self.client.get(reverse(name, args=[self.other.pk])).status_code, 404)

    def test_member_contributes_own_piece_to_someone_elses_workshop_gallery(self):
        response = self.client.post(reverse('gallery_entry', args=[self.gallery.pk]), {
            'piece': self.piece.pk, 'title': 'Mi taza para el taller', 'description': 'Presentación elegida',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.gallery.entries.get().piece_id, self.piece.pk)
        self.assertFalse(can_read(self.piece, self.owner))
        # Contributing a piece never changes ownership or shares its private notebook.
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.owner_id, self.member.pk)
        self.assertFalse(self.piece.shared_groups.exists())

    def test_contribution_does_not_allow_stealing_another_authors_piece(self):
        response = self.client.post(reverse('gallery_entry', args=[self.gallery.pk]), {
            'piece': self.foreign_piece.pk, 'title': 'Forged',
        })
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.gallery.entries.exists())
        self.assertEqual(self.client.post(reverse('gallery_entry', args=[self.gallery.pk]), {'piece': 'bad-id'}).status_code, 404)

    def test_private_material_stays_redacted_even_with_legacy_sharing(self):
        GalleryEntry.objects.create(gallery=self.gallery, piece=self.piece, title=self.piece.name)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('gallery_manage', args=[self.gallery.pk]))
        self.assertContains(response, 'Material privado')
        self.assertContains(response, 'Gres del taller')
        for private in ['ESMALTE SECRETO', 'RECETA SECRETA', 'NOTA PRIVADA DEL AUTOR']:
            self.assertNotContains(response, private)
        self.assertEqual(self.client.get(reverse('glaze', args=[self.material.pk])).status_code, 404)
        self.material.shared_groups.add(self.workshop)
        self.assertNotContains(self.client.get(reverse('gallery_manage', args=[self.gallery.pk])), self.material.name)
        self.assertEqual(self.client.get(reverse('glaze', args=[self.material.pk])).status_code, 404)

    def test_selected_photos_only_and_membership_revocation(self):
        selected, private = save_photos([image_file('selected.png'), image_file('private.png')], piece=self.piece)
        entry = GalleryEntry.objects.create(gallery=self.gallery, piece=self.piece, title='Taza')
        entry.photos.add(selected)
        self.client.force_login(self.owner)
        response = self.client.get(reverse('photo', args=[selected.pk]))
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        self.assertEqual(self.client.get(reverse('photo', args=[private.pk])).status_code, 404)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse('gallery_manage', args=[self.gallery.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('photo', args=[selected.pk])).status_code, 404)
        self.workshop.members.add(self.outsider)
        response = self.client.get(reverse('photo', args=[selected.pk]))
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        self.workshop.members.remove(self.outsider)
        self.assertEqual(self.client.get(reverse('photo', args=[selected.pk])).status_code, 404)

    def test_same_presentation_in_multiple_galleries_keeps_its_own_title(self):
        self.client.post(reverse('piece_edit', args=[self.piece.pk]), {
            'name': 'Taza actualizada', 'stage': 'raw', 'started_on': '2026-10-27',
            'galleries_present': '1', 'galleries': [self.gallery.pk, self.personal_gallery.pk],
        })
        self.piece.refresh_from_db()
        self.assertEqual(self.piece.name, 'Taza actualizada')
        self.assertEqual(self.piece.gallery_entries.count(), 2)
        self.assertEqual(Piece.objects.filter(owner=self.member).count(), 1)
        self.piece.name = 'Nombre cambiado de nuevo'
        self.piece.save()
        for entry in self.piece.gallery_entries.select_related('piece'):
            self.assertEqual(entry.public_presentation.display_title, 'Taza actualizada')
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('gallery_manage', args=[self.gallery.pk])), 'Taza actualizada')

    def test_removing_from_gallery_preserves_piece_and_other_gallery(self):
        entry = GalleryEntry.objects.create(gallery=self.gallery, piece=self.piece, title='Taza')
        GalleryEntry.objects.create(gallery=self.personal_gallery, piece=self.piece, title='Taza')
        response = self.client.post(reverse('gallery_remove', args=[self.gallery.pk, entry.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Piece.objects.filter(pk=self.piece.pk).exists())
        self.assertEqual(self.piece.gallery_entries.get().gallery_id, self.personal_gallery.pk)

    def test_member_cannot_change_gallery_or_other_members_entries(self):
        entry = GalleryEntry.objects.create(gallery=self.gallery, piece=self.foreign_piece, title='Otra')
        self.assertEqual(self.client.get(reverse('gallery_edit', args=[self.gallery.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('gallery_remove', args=[self.gallery.pk, entry.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('gallery_entry_edit', args=[self.gallery.pk, entry.pk])).status_code, 404)

    def test_admin_can_moderate_without_taking_authorship(self):
        gallery = Gallery.objects.create(owner=self.member, workshop=self.workshop, name='Creada por miembro', audience='group')
        self.client.force_login(self.owner)
        response = self.client.post(reverse('gallery_edit', args=[gallery.pk]), {
            'name': 'Revisada', 'workshop': self.other.pk, 'audience': 'group',
        })
        self.assertEqual(response.status_code, 302)
        gallery.refresh_from_db()
        self.assertEqual(gallery.owner_id, self.member.pk)
        self.assertEqual(gallery.workshop_id, self.workshop.pk)

    def test_member_can_create_workshop_gallery_but_not_in_an_unrelated_workshop(self):
        response = self.client.post(reverse('gallery_new'), {
            'name': 'Galería compartida nueva', 'workshop': self.workshop.pk, 'audience': 'group',
        })
        self.assertEqual(response.status_code, 302)
        gallery = Gallery.objects.get(name='Galería compartida nueva')
        self.assertEqual(gallery.audience, 'group')
        self.assertEqual(gallery.owner_id, self.member.pk)
        self.assertEqual(self.client.post(reverse('gallery_new'), {
            'name': 'No permitida', 'workshop': self.other.pk, 'audience': 'group',
        }).status_code, 200)
        self.assertFalse(Gallery.objects.filter(name='No permitida').exists())

    def test_private_visibility_cannot_silently_be_broadened_by_workshop_selection(self):
        response = self.client.post(reverse('gallery_new'), {
            'name': 'Debe permanecer sin publicar', 'workshop': self.workshop.pk, 'audience': 'private',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('audience', response.context['form'].errors)
        self.assertFalse(Gallery.objects.filter(name='Debe permanecer sin publicar').exists())

    def test_even_administrators_cannot_share_a_material_with_multiple_workshops(self):
        self.other.members.add(self.member)
        self.workshop.administrators.add(self.member)
        self.other.administrators.add(self.member)
        response = self.client.post(reverse('glaze_edit', args=[self.material.pk]), {
            'name': 'Esmalte compartido', 'kind': 'commercial', 'material_type': 'glaze',
            'shared_groups': [self.workshop.pk, self.other.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('__all__', response.context['form'].errors)
        self.material.refresh_from_db()
        self.assertFalse(self.material.shared_groups.exists())
        self.assertFalse(can_read(self.material, self.owner))
        self.assertFalse(can_read(self.material, self.outsider))
        self.assertEqual(Glaze.objects.filter(pk=self.material.pk).count(), 1)

    def test_unified_library_filters_origin_without_showing_other_workshops(self):
        response = self.client.get(reverse('glazes'), {'origin': 'personal'})
        self.assertContains(response, self.material.name)
        self.assertNotContains(response, self.shared_material.name)
        response = self.client.get(reverse('glazes'), {'origin': self.workshop.pk})
        self.assertContains(response, self.shared_material.name)
        self.assertNotContains(response, self.material.name)
        for origin in ['bad-id', str(self.other.pk)]:
            response = self.client.get(reverse('glazes'), {'origin': origin})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['page'].paginator.count, 0)

    def test_member_cannot_add_materials_to_workshop_even_through_sharing(self):
        response = self.client.post(reverse('glaze_new'), {
            'name': 'Publicación no autorizada', 'kind': 'commercial', 'material_type': 'glaze',
            'shared_groups': [self.workshop.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('__all__', response.context['form'].errors)
        self.assertFalse(Glaze.objects.filter(name='Publicación no autorizada').exists())
        self.assertEqual(self.client.get(reverse('workshop_materials', args=[self.workshop.pk])).status_code, 404)

    def test_workshop_bookmarks_redirect_to_the_unified_gallery_catalog(self):
        self.assertRedirects(self.client.get(reverse('workshop', args=[self.workshop.pk])), reverse('galleries'))
        response = self.client.get(reverse('galleries'))
        self.assertContains(response, 'mobile-four-nav')
        self.assertNotContains(response, 'TALLER ACTIVO')
        self.assertNotContains(response, 'Administrar taller')
        self.assertNotContains(response, 'Materiales del taller')
        self.assertIn(self.gallery, response.context['galleries'])
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse('galleries')), 'Administrar taller')

    def test_public_gallery_does_not_open_private_notebook(self):
        self.gallery.audience = 'public'
        self.gallery.save()
        GalleryEntry.objects.create(gallery=self.gallery, piece=self.piece, title='Nombre elegido')
        self.client.logout()
        response = self.client.get(reverse('gallery', args=[self.gallery.pk]))
        self.assertContains(response, 'Nombre elegido')
        self.assertNotContains(response, self.material.name)
        self.assertNotContains(response, self.piece.notes)
        self.assertEqual(self.client.get(reverse('gallery_manage', args=[self.gallery.pk])).status_code, 302)

    def test_membership_revocation_blocks_contribution_and_forged_piece_gallery_selection(self):
        self.workshop.members.remove(self.member)
        self.assertEqual(self.client.get(reverse('gallery_entry', args=[self.gallery.pk])).status_code, 404)
        response = self.client.post(reverse('piece_edit', args=[self.piece.pk]), {
            'name': 'No publicar', 'stage': 'raw', 'started_on': '2026-10-27',
            'galleries': [self.gallery.pk], 'galleries_present': '1',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('galleries', response.context['form'].errors)
        self.assertFalse(self.gallery.entries.exists())

    def test_contribution_and_remove_require_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.member)
        self.assertEqual(csrf_client.post(reverse('gallery_entry', args=[self.gallery.pk]), {
            'piece': self.piece.pk, 'title': 'Taza',
        }).status_code, 403)

    def test_upgrade_preserves_gallery_ids_entries_and_ambiguous_legacy_shares(self):
        legacy = Gallery.objects.create(owner=self.owner, name='Colección antigua', audience='group')
        legacy.shared_groups.add(self.workshop)
        entry = GalleryEntry.objects.create(gallery=legacy, piece=self.piece, title='Título antiguo')
        multi = Gallery.objects.create(owner=self.owner, name='Compartida con dos', audience='group')
        multi.shared_groups.add(self.workshop, self.other)
        migration = importlib.import_module('studio.migrations.0011_gallery_workshop')
        migration.assign_existing_galleries(apps, SimpleNamespace(connection=connection))
        legacy.refresh_from_db()
        multi.refresh_from_db()
        self.assertEqual(legacy.workshop_id, self.workshop.pk)
        self.assertEqual(legacy.entries.get().pk, entry.pk)
        self.assertIsNone(multi.workshop_id)
        self.assertEqual(multi.shared_groups.count(), 2)
