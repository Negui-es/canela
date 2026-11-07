from tempfile import TemporaryDirectory

from django.conf import settings
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .forms import MoldForm, PieceForm
from .models import Circle, Mold, Piece, Photo, User
from .permissions import can_read
from .services import save_photos
from .tests import image_file


@override_settings(SECURE_SSL_REDIRECT=False)
class MoldWorkshopTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        temp = TemporaryDirectory(dir=settings.BASE_DIR / 'data')
        self.addCleanup(temp.cleanup)
        storage = override_settings(MEDIA_ROOT=temp.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.admin = User.objects.create_user('mold-admin')
        self.member = User.objects.create_user('mold-member')
        self.stranger = User.objects.create_user('mold-stranger')
        self.root = Circle.objects.create(owner=self.admin, name='Taller')
        self.child = Circle.objects.create(owner=self.admin, parent=self.root, name='Clase')
        self.child.members.add(self.member)
        self.catalog = Mold.objects.create(owner=self.member, group=self.root, name='Molde del taller')
        self.personal = Mold.objects.create(owner=self.member, name='Molde personal')
        self.client.force_login(self.member)

    def payload(self, **extra):
        return {'name': 'Molde nuevo', 'kind': 'Presión', 'material': 'Escayola', 'parts': 1, 'state': 'available', **extra}

    def test_member_reads_parent_catalog_in_library_and_piece_picker_but_cannot_manage(self):
        response = self.client.get(reverse('molds'))
        self.assertContains(response, self.catalog.name)
        self.assertContains(response, self.personal.name)
        self.assertContains(self.client.get(reverse('molds'), {'origin': self.child.pk}), self.catalog.name)
        self.assertIn(self.catalog, PieceForm(user=self.member).fields['mold'].queryset)
        self.assertNotContains(self.client.get(reverse('mold', args=[self.catalog.pk])), reverse('mold_edit', args=[self.catalog.pk]))
        self.assertEqual(self.client.get(reverse('mold_edit', args=[self.catalog.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('mold_delete', args=[self.catalog.pk]), {'confirm_delete': 'yes'}).status_code, 404)
        self.assertFalse(MoldForm(user=self.member).fields['group'].queryset.exists())
        self.assertNotIn('shared_groups', MoldForm(user=self.member).fields)

    def test_only_admin_creates_workshop_mold_and_existing_ownership_is_retained(self):
        self.assertEqual(self.client.post(reverse('mold_new'), self.payload(group=self.root.pk)).status_code, 200)
        self.assertFalse(Mold.objects.filter(name='Molde nuevo').exists())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('mold_new'), self.payload(group=self.child.pk)).status_code, 302)
        mold = Mold.objects.get(name='Molde nuevo')
        self.assertEqual(mold.group, self.child)
        self.assertTrue(can_read(mold, self.member))
        self.assertEqual(self.client.post(reverse('mold_edit', args=[self.catalog.pk]), self.payload(group='')).status_code, 302)
        self.catalog.refresh_from_db()
        self.assertEqual(self.catalog.owner, self.member)
        self.assertEqual(self.catalog.group, self.root)

    def test_personal_legacy_sharing_does_not_publish_and_group_photos_follow_permissions(self):
        self.personal.shared_groups.add(self.root)
        self.assertFalse(can_read(self.personal, self.admin))
        photo = save_photos([image_file()], mold=self.catalog)[0]
        self.assertEqual(self.client.get(reverse('photos_manage', kwargs={'kind': 'mold', 'pk': self.catalog.pk})).status_code, 404)
        response = self.client.get(reverse('photo', args=[photo.pk]))
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('photos_manage', kwargs={'kind': 'mold', 'pk': self.catalog.pk})).status_code, 200)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse('photo', args=[photo.pk])).status_code, 404)

    def test_mold_deletion_protects_piece_history_and_cleans_only_unlinked_files(self):
        piece = Piece.objects.create(owner=self.member, name='Pieza', mold=self.catalog)
        self.client.force_login(self.admin)
        url = reverse('mold_delete', args=[self.catalog.pk])
        self.assertEqual(self.client.post(url, {'confirm_delete': 'yes'}).status_code, 409)
        piece.refresh_from_db()
        self.assertEqual(piece.mold, self.catalog)
        photo = save_photos([image_file()], mold=self.personal)[0]
        self.client.force_login(self.member)
        url = reverse('mold_delete', args=[self.personal.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertRedirects(self.client.post(url, {'confirm_delete': 'yes'}), reverse('molds'))
        self.assertFalse(Mold.objects.filter(pk=self.personal.pk).exists())
        self.assertFalse(Photo.objects.filter(pk=photo.pk).exists())
        self.assertFalse(photo.image.storage.exists(photo.image.name))

    def test_revoked_mold_link_is_retained_without_exposing_private_name(self):
        mold = Mold.objects.create(owner=self.stranger, name='NOMBRE SECRETO')
        piece = Piece.objects.create(owner=self.member, name='Pieza', mold=mold)
        response = self.client.get(reverse('piece_edit', args=[piece.pk]))
        self.assertNotContains(response, mold.name)
        response = self.client.post(reverse('piece_edit', args=[piece.pk]), {'name': piece.name, 'stage': 'raw', 'started_on': '2026-10-28'})
        self.assertEqual(response.status_code, 302)
        piece.refresh_from_db()
        self.assertEqual(piece.mold, mold)

    def test_four_creation_choices_and_workshop_prefill(self):
        self.client.force_login(self.admin)
        glaze = self.client.get(reverse('glaze_new'), {'group': self.root.pk})
        self.assertContains(glaze, reverse('mold_new') + '?group=' + str(self.root.pk))
        mold = self.client.get(reverse('mold_new'), {'group': self.root.pk})
        self.assertEqual(str(mold.context['form']['group'].value()), str(self.root.pk))
        self.assertContains(mold, 'aria-current="page"')
        self.assertNotContains(mold, 'name="shared_groups"')

    def test_group_mold_survives_creator_account_deletion(self):
        identifier = self.catalog.pk
        self.member.delete()
        self.catalog.refresh_from_db()
        self.assertEqual(self.catalog.pk, identifier)
        self.assertIsNone(self.catalog.owner_id)
        self.assertEqual(self.catalog.group, self.root)


class MoldWorkshopMigrationTests(TransactionTestCase):
    def test_existing_mold_owner_piece_photo_and_legacy_links_survive_upgrade(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        original_targets = executor.loader.graph.leaf_nodes()
        previous = [('studio', '0012_piece_clay_material')]
        current = [('studio', '0013_mold_workshop')]
        try:
            executor.migrate(previous)
            old = executor.loader.project_state(previous).apps
            user = old.get_model('studio', 'User').objects.create(username='migration-mold')
            circle = old.get_model('studio', 'Circle').objects.create(owner_id=user.pk, name='Taller')
            mold = old.get_model('studio', 'Mold').objects.create(owner_id=user.pk, name='Molde existente', parts=3, notes='Conservar')
            mold.shared_groups.add(circle)
            piece = old.get_model('studio', 'Piece').objects.create(owner_id=user.pk, name='Pieza', mold_id=mold.pk)
            photo = old.get_model('studio', 'Photo').objects.create(mold_id=mold.pk, original='original.png', image='image.jpg', thumbnail='thumb.jpg')
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            new = executor.loader.project_state(current).apps
            updated = new.get_model('studio', 'Mold').objects.get(pk=mold.pk)
            self.assertEqual((updated.owner_id, updated.group_id, updated.name, updated.parts, updated.notes), (user.pk, None, 'Molde existente', 3, 'Conservar'))
            self.assertTrue(updated.shared_groups.filter(pk=circle.pk).exists())
            self.assertEqual(new.get_model('studio', 'Piece').objects.get(pk=piece.pk).mold_id, mold.pk)
            self.assertEqual(new.get_model('studio', 'Photo').objects.get(pk=photo.pk).mold_id, mold.pk)
        finally:
            MigrationExecutor(connection).migrate(original_targets)
