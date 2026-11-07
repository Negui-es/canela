from datetime import timedelta
from importlib import import_module
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from django.apps import apps
from django.conf import settings
from django.core import signing
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from .models import Circle, Gallery, GalleryEntry, Piece, PiecePresentation, User
from .services import save_photos
from .tests import image_file


@override_settings(SECURE_SSL_REDIRECT=False, LANGUAGE_CODE='es')
class InspirationTests(TestCase):
    def setUp(self):
        language = translation.override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        media = TemporaryDirectory(dir=settings.BASE_DIR / 'data')
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.owner = User.objects.create_user('inspiration-owner', display_name='Ana')
        self.other = User.objects.create_user('inspiration-other')
        self.piece = Piece.objects.create(owner=self.owner, name='Nombre privado', notes='NOTAS SECRETAS', technique='TECNICA PRIVADA')
        self.first, self.second = save_photos([image_file(), image_file()], piece=self.piece)
        self.client.force_login(self.owner)
        self.edit = reverse('presentation_edit', args=[self.piece.pk])
        self.publish = reverse('presentation_publish', args=[self.piece.pk])
        self.feed = reverse('inspiration')

    def save(self, **changes):
        data = {'title': 'Cuenco público', 'description': 'Descripción elegida', 'photos': [self.first.pk], 'cover': self.first.pk}
        data.update(changes)
        return self.client.post(self.edit, data)

    def photo_status(self, photo, client=None):
        response = (client or Client()).get(reverse('photo', args=[photo.pk]))
        status = response.status_code
        if response.streaming:
            b''.join(response.streaming_content)
        return status

    def test_draft_and_publication_do_not_expose_private_fields_or_photos(self):
        self.assertEqual(self.save().status_code, 302)
        guest = Client()
        self.assertNotContains(guest.get(self.feed), 'Cuenco público')
        self.assertEqual(self.photo_status(self.first), 404)
        self.assertEqual(self.save(intent='publish').status_code, 302)
        response = guest.get(self.feed)
        self.assertContains(response, 'Cuenco público')
        for secret in ['Nombre privado', 'NOTAS SECRETAS', 'TECNICA PRIVADA', str(self.second.pk), self.publish]:
            self.assertNotContains(response, secret)
        self.assertEqual(self.photo_status(self.first), 200)
        self.assertEqual(self.photo_status(self.second), 404)
        self.assertEqual(guest.get(reverse('piece', args=[self.piece.pk])).status_code, 302)

    def test_same_presentation_in_all_galleries_and_independent_removal(self):
        galleries = [Gallery.objects.create(owner=self.owner, name=f'Galería {i}', audience='public') for i in range(2)]
        self.save(intent='publish')
        for gallery in galleries:
            self.assertEqual(self.client.post(reverse('gallery_entry', args=[gallery.pk]), {
                'piece': self.piece.pk, 'title': 'Título común', 'description': 'Texto común', 'photos': [self.second.pk], 'cover': self.second.pk,
            }).status_code, 302)
        self.assertEqual(PiecePresentation.objects.filter(piece=self.piece).count(), 1)
        for gallery in galleries:
            response = Client().get(reverse('gallery', args=[gallery.pk]))
            self.assertContains(response, 'Título común')
            self.assertContains(response, str(self.second.pk))
            self.assertNotContains(response, str(self.first.pk))
        self.assertEqual(self.photo_status(self.first), 404)
        self.client.post(self.publish, {'action': 'unpublish'})
        self.assertNotContains(Client().get(self.feed), 'Título común')
        self.assertEqual(self.photo_status(self.second), 200)
        for gallery in galleries:
            self.client.post(reverse('gallery_remove', args=[gallery.pk, gallery.entries.get().pk]))
        self.assertEqual(self.photo_status(self.second), 404)
        self.assertTrue(PiecePresentation.objects.filter(piece=self.piece).exists())

    def test_photos_and_cover_cannot_be_forged(self):
        foreign = Piece.objects.create(owner=self.other, name='Foreign')
        photo = save_photos([image_file()], piece=foreign)[0]
        for changes in [{'photos': [photo.pk]}, {'cover': photo.pk}, {'cover': self.second.pk}]:
            response = self.save(**changes)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            self.assertFalse(PiecePresentation.objects.filter(piece=self.piece).exists())
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.edit).status_code, 404)
        self.assertEqual(self.client.post(self.publish, {'action': 'publish'}).status_code, 404)

    def test_publication_needs_a_photo_and_csrf_and_republishing_keeps_date(self):
        self.save(photos=[], cover='', intent='publish')
        self.assertFalse(PiecePresentation.objects.filter(piece=self.piece).exists())
        self.save(intent='publish')
        presentation = PiecePresentation.objects.get(piece=self.piece)
        first_date = presentation.published_at
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.owner)
        self.assertEqual(csrf.post(self.publish, {'action': 'unpublish'}).status_code, 403)
        self.assertEqual(self.client.get(self.publish).status_code, 405)
        self.assertEqual(self.client.post(self.publish, {'action': 'invalid'}).status_code, 400)
        self.client.post(self.publish, {'action': 'unpublish'})
        self.client.post(self.publish, {'action': 'publish'})
        presentation.refresh_from_db()
        self.assertEqual(presentation.published_at, first_date)
        self.save(photos=[], cover='')
        self.assertTrue(PiecePresentation.objects.get(pk=presentation.pk).photos.exists())

    def test_deleting_last_photo_withdraws_publication(self):
        self.save(intent='publish')
        self.client.post(reverse('photo_delete', args=[self.first.pk]), {'confirm_delete': 'yes'})
        self.assertFalse(PiecePresentation.objects.get(piece=self.piece).published)
        self.assertNotContains(Client().get(self.feed), 'Cuenco público')

    def test_canonical_photos_follow_workshop_membership_and_explicit_selection(self):
        circle = Circle.objects.create(owner=self.owner, name='Taller')
        circle.members.add(self.owner, self.other)
        gallery = Gallery.objects.create(owner=self.owner, workshop=circle, name='Clase', audience='group')
        self.save()
        legacy = GalleryEntry.objects.create(gallery=gallery, piece=self.piece, title='Old')
        legacy.photos.add(self.second)
        member = Client()
        member.force_login(self.other)
        self.assertEqual(self.photo_status(self.first, member), 200)
        self.assertEqual(self.photo_status(self.second, member), 404)
        self.assertEqual(self.photo_status(self.first), 404)
        circle.members.remove(self.other)
        self.assertEqual(self.photo_status(self.first, member), 404)
        self.save(intent='publish')
        self.assertEqual(self.photo_status(self.first, member), 200)
        self.client.post(self.publish, {'action': 'unpublish'})
        self.assertEqual(self.photo_status(self.first, member), 404)

    def test_private_piece_edits_do_not_update_the_public_presentation(self):
        self.save(intent='publish')
        gallery = Gallery.objects.create(owner=self.owner, name='Colección', audience='public')
        self.client.post(reverse('piece_edit', args=[self.piece.pk]), {
            'name': 'Nuevo nombre privado', 'stage': 'raw', 'started_on': '2026-10-28',
            'galleries_present': '1', 'galleries': [gallery.pk],
        })
        presentation = PiecePresentation.objects.get(piece=self.piece)
        self.assertEqual(presentation.title, 'Cuenco público')
        self.assertEqual(list(presentation.photos.all()), [self.first])
        self.assertNotContains(Client().get(self.feed), 'Nuevo nombre privado')
        self.assertContains(Client().get(reverse('gallery', args=[gallery.pk])), 'Cuenco público')

    def test_gallery_cover_uses_the_selected_presentation_cover(self):
        self.save(photos=[self.first.pk, self.second.pk], cover=self.second.pk)
        gallery = Gallery.objects.create(owner=self.owner, name='Colección')
        GalleryEntry.objects.create(gallery=gallery, piece=self.piece, title='Old')
        response = self.client.get(reverse('galleries'))
        self.assertEqual(next(g for g in response.context['galleries'] if g.pk == gallery.pk).cover_photo_id, self.second.pk)

    def test_cursor_is_stable_when_new_publications_arrive_and_dates_tie(self):
        date = timezone.now() - timedelta(days=1)
        for i in range(30):
            piece = Piece.objects.create(owner=self.owner, name=f'Piece {i}')
            presentation = PiecePresentation.objects.create(piece=piece, title=f'Public {i}', published=True, published_at=date)
            # Real photos belong to the piece, including when rendering a page.
            photo = save_photos([image_file()], piece=piece)[0]
            presentation.photos.add(photo)
        first = self.client.get(self.feed)
        initial_ids = {p.pk for p in first.context['presentations']}
        self.assertEqual(len(initial_ids), 24)
        self.save(intent='publish')
        second = self.client.get(first.context['next_url'], HTTP_X_INSPIRATION_BATCH='1')
        rest = {p.pk for p in second.context['presentations']}
        self.assertEqual(len(rest), 6)
        self.assertFalse(initial_ids & rest)
        self.assertNotContains(second, '<html')
        self.assertEqual(self.client.get(self.feed + '?cursor=broken').status_code, 400)
        invalid = signing.dumps(['bad-date', 1], salt='inspiration')
        self.assertEqual(self.client.get(self.feed, {'cursor': invalid}).status_code, 400)

    def test_migration_only_uses_common_information_and_keeps_originals(self):
        private = Gallery.objects.create(owner=self.owner, name='Private')
        public = Gallery.objects.create(owner=self.owner, name='Public', audience='public')
        a = GalleryEntry.objects.create(gallery=private, piece=self.piece, title='Hidden title', description='PRIVATE DESCRIPTION')
        b = GalleryEntry.objects.create(gallery=public, piece=self.piece, title='Public title', description='Public description')
        a.photos.set([self.first, self.second])
        b.photos.set([self.first])
        migration = import_module('studio.migrations.0017_unify_presentations')
        migration.unify(apps, SimpleNamespace(connection=connection))
        presentation = PiecePresentation.objects.get(piece=self.piece)
        self.assertTrue(presentation.needs_review)
        self.assertFalse(presentation.published)
        self.assertEqual(presentation.description, '')
        self.assertEqual(list(presentation.photos.all()), [self.first])
        self.assertContains(self.client.get(self.edit), 'PRIVATE DESCRIPTION')
        self.assertNotContains(Client().get(reverse('gallery', args=[public.pk])), 'PRIVATE DESCRIPTION')
        self.assertEqual(GalleryEntry.objects.get(pk=a.pk).description, 'PRIVATE DESCRIPTION')
