from tempfile import TemporaryDirectory
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .models import Circle, Gallery, GalleryEntry, Piece, User
from .services import save_photos
from .tests import image_file


@override_settings(SECURE_SSL_REDIRECT=False)
class GalleryCatalogTests(TestCase):
    def setUp(self):
        media = TemporaryDirectory(dir=Path(settings.BASE_DIR) / 'data')
        self.addCleanup(media.cleanup)
        storage = override_settings(MEDIA_ROOT=media.name)
        storage.enable()
        self.addCleanup(storage.disable)
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.admin = User.objects.create_user('gallery-catalog-admin')
        self.member = User.objects.create_user('gallery-catalog-member')
        self.other = User.objects.create_user('gallery-catalog-other')
        self.root = Circle.objects.create(owner=self.admin, name='Serendipia')
        self.child = Circle.objects.create(owner=self.admin, parent=self.root, name='Martes')
        self.child.members.add(self.member)
        self.sibling = Circle.objects.create(owner=self.other, parent=self.root, name='Taller ajeno')
        self.personal = Gallery.objects.create(owner=self.member, name='Personal propia')
        self.parent_gallery = Gallery.objects.create(owner=self.admin, workshop=self.root, name='Colección del taller', audience='group')
        self.child_gallery = Gallery.objects.create(owner=self.member, workshop=self.child, name='Colección de clase', audience='group')
        self.foreign = Gallery.objects.create(owner=self.other, workshop=self.sibling, name='NO DESCUBRIR', audience='public')
        self.private = Gallery.objects.create(owner=self.admin, name='PRIVADA AJENA', audience='private')
        self.private.shared_groups.add(self.root)
        self.shared = Gallery.objects.create(owner=self.admin, name='Personal compartida', audience='group')
        self.shared.shared_groups.add(self.root, self.child)
        self.client.force_login(self.member)

    def test_cover_uses_only_explicitly_selected_gallery_photos(self):
        piece = Piece.objects.create(owner=self.admin, name='Pieza privada')
        selected, private = save_photos([image_file(), image_file()], piece=piece)
        entry = GalleryEntry.objects.create(gallery=self.parent_gallery, piece=piece, title='Compartida')
        entry.photos.add(selected)
        response = self.client.get(reverse('galleries'))
        catalog = {gallery.pk: gallery for gallery in response.context['galleries']}
        self.assertEqual(catalog[self.parent_gallery.pk].cover_photo_id, selected.pk)
        self.assertContains(response, reverse('photo', args=[selected.pk]) + '?thumb=1')
        self.assertNotContains(response, reverse('photo', args=[private.pk]))
        self.assertEqual(self.client.get(reverse('photo', args=[selected.pk]) + '?thumb=1').status_code, 200)
        self.assertEqual(self.client.get(reverse('photo', args=[private.pk])).status_code, 404)
        entry.photos.clear()
        response = self.client.get(reverse('galleries'))
        self.assertNotContains(response, reverse('photo', args=[selected.pk]))
        self.assertEqual(self.client.get(reverse('photo', args=[selected.pk])).status_code, 404)

    def test_gallery_without_selected_photos_uses_illustration(self):
        piece = Piece.objects.create(owner=self.admin, name='Historial privado')
        photo = save_photos([image_file()], piece=piece)[0]
        GalleryEntry.objects.create(gallery=self.parent_gallery, piece=piece, title='Sin fotos')
        response = self.client.get(reverse('galleries'))
        self.assertContains(response, 'gallery-placeholder.svg')
        self.assertNotContains(response, reverse('photo', args=[photo.pk]))

    def test_catalog_lists_personal_and_workshop_galleries_together_without_leaking_others(self):
        piece = Piece.objects.create(owner=self.member, name='Pieza')
        GalleryEntry.objects.create(gallery=self.parent_gallery, piece=piece, title=piece.name)
        response = self.client.get(reverse('galleries'))
        self.assertEqual(set(response.context['galleries']), {self.personal, self.parent_gallery, self.child_gallery, self.shared})
        catalog = {gallery.pk: gallery for gallery in response.context['galleries']}
        self.assertEqual(catalog[self.parent_gallery.pk].entry_total, 1)
        self.assertContains(response, 'gallery-catalog-grid')
        self.assertNotContains(response, 'gallery-workshop-group')
        self.assertContains(response, 'Serendipia / Martes')
        self.assertContains(response, 'Taller ·')
        self.assertNotContains(response, self.foreign.name)
        self.assertNotContains(response, self.private.name)
        self.assertNotContains(response, self.sibling.name)
        self.assertNotContains(response, reverse('workshop_galleries', args=[self.child.pk]))

    def test_workshop_gallery_page_keeps_gallery_navigation_and_workshop_identity(self):
        for url in [reverse('gallery_manage', args=[self.child_gallery.pk]), reverse('gallery_new') + '?workshop=' + str(self.child.pk)]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            bar = html.split('<nav class="mobile-nav ', 1)[1].split('</nav>', 1)[0]
            self.assertIn('href="' + reverse('galleries') + '" class="active"', bar)
            self.assertEqual(bar.count('aria-current="page"'), 1)
            self.assertContains(response, reverse('galleries'))
        detail = self.client.get(reverse('gallery_manage', args=[self.child_gallery.pk]))
        self.assertContains(detail, 'Serendipia / Martes')
        self.assertNotContains(detail, reverse('workshop_galleries', args=[self.child.pk]))

    def test_admin_workshop_menu_has_management_only_and_old_links_still_work(self):
        self.client.force_login(self.admin)
        html = self.client.get(reverse('galleries')).content.decode()
        menu = html.split('<section class="workshop-navigation">', 1)[1].split('</section>', 1)[0]
        self.assertIn(reverse('circle', args=[self.root.pk]), menu)
        self.assertNotIn('Galerías', menu)
        self.assertNotIn(reverse('workshop_galleries', args=[self.root.pk]), menu)
        response = self.client.get(reverse('workshop_galleries', args=[self.root.pk]))
        self.assertRedirects(response, reverse('galleries'))

    def test_revoking_membership_removes_workshop_and_shared_galleries_without_changing_records(self):
        self.child.members.remove(self.member)
        response = self.client.get(reverse('galleries'))
        self.assertEqual(response.context['galleries'], [self.personal])
        self.assertNotContains(response, self.parent_gallery.name)
        self.assertEqual(self.client.get(reverse('gallery_manage', args=[self.child_gallery.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('workshop_galleries', args=[self.child.pk])).status_code, 404)
        self.assertTrue(Gallery.objects.filter(pk=self.child_gallery.pk).exists())
