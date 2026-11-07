from tempfile import TemporaryDirectory

from django.conf import settings
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .models import Circle, Glaze, GlazeUse, Ingredient, Photo, Piece, RecipeVersion, Sample, User
from .services import delete_material, save_photos
from .tests import image_file


@override_settings(SECURE_SSL_REDIRECT=False)
class MaterialDeleteTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        temporary = TemporaryDirectory(dir=settings.BASE_DIR / 'data')
        self.addCleanup(temporary.cleanup)
        storage = override_settings(MEDIA_ROOT=temporary.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.owner = User.objects.create_user('material-delete-owner')
        self.admin = User.objects.create_user('material-delete-admin')
        self.member = User.objects.create_user('material-delete-member')
        self.workshop = Circle.objects.create(owner=self.admin, name='Taller')
        self.workshop.members.add(self.owner, self.member)
        self.personal = Glaze.objects.create(owner=self.owner, name='Material propio')
        self.group_material = Glaze.objects.create(owner=self.owner, group=self.workshop, name='Material del taller')
        self.client.force_login(self.owner)

    def test_only_personal_owner_and_workshop_administrators_have_delete_access(self):
        self.personal.shared_groups.add(self.workshop)
        for actor, material, allowed in [
            (self.owner, self.personal, True), (self.admin, self.personal, False),
            (self.member, self.personal, False), (self.owner, self.group_material, False),
            (self.member, self.group_material, False), (self.admin, self.group_material, True),
        ]:
            self.client.force_login(actor)
            url = reverse('material_delete', args=[material.pk])
            detail = self.client.get(reverse('glaze', args=[material.pk]))
            if allowed:
                self.assertContains(detail, url)
                self.assertEqual(self.client.get(url).status_code, 200)
            else:
                self.assertNotIn(url.encode(), detail.content)
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.post(url, {'confirm_delete': 'yes'}).status_code, 404)
            self.assertTrue(Glaze.objects.filter(pk=material.pk).exists())

    def test_parent_administrator_can_delete_child_material_without_owning_it(self):
        child = Circle.objects.create(owner=self.owner, parent=self.workshop, name='Clase')
        material = Glaze.objects.create(owner=self.owner, group=child, name='Barro de clase', material_type='clay')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('material_delete', args=[material.pk]), {'confirm_delete': 'yes'})
        self.assertRedirects(response, reverse('glazes') + '?material_type=clay')
        self.assertFalse(Glaze.objects.filter(pk=material.pk).exists())

    def test_get_and_unconfirmed_post_never_delete_and_other_methods_are_rejected(self):
        url = reverse('material_delete', args=[self.personal.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {'confirm_delete': 'no'}).status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.assertTrue(Glaze.objects.filter(pk=self.personal.pk).exists())

    def test_all_material_categories_can_be_deleted(self):
        for category in Glaze.MaterialType.values:
            material = Glaze.objects.create(owner=self.owner, name=category, material_type=category)
            response = self.client.post(reverse('material_delete', args=[material.pk]), {'confirm_delete': 'yes'})
            self.assertRedirects(response, reverse('glazes') + '?material_type=' + category)
            self.assertFalse(Glaze.objects.filter(pk=material.pk).exists())

    def test_own_recipe_samples_and_photos_are_deleted_only_after_commit(self):
        version = RecipeVersion.objects.create(glaze=self.personal, number=1)
        Ingredient.objects.create(version=version, name='Caolín', percentage=100)
        sample = Sample.objects.create(glaze=self.personal, recipe_version=version, temperature=1200)
        photos = [save_photos([image_file()], glaze=self.personal)[0], save_photos([image_file()], sample=sample)[0]]
        other = save_photos([image_file()], glaze=self.group_material)[0]
        files = [field for photo in photos for field in [photo.original, photo.image, photo.thumbnail]]
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('material_delete', args=[self.personal.pk]), {'confirm_delete': 'yes'})
            self.assertEqual(response.status_code, 302)
            self.assertTrue(all(field.storage.exists(field.name) for field in files))
        self.assertFalse(Glaze.objects.filter(pk=self.personal.pk).exists())
        self.assertFalse(RecipeVersion.objects.filter(pk=version.pk).exists())
        self.assertFalse(Sample.objects.filter(pk=sample.pk).exists())
        self.assertFalse(Photo.objects.filter(pk__in=[photo.pk for photo in photos]).exists())
        self.assertFalse(any(field.storage.exists(field.name) for field in files))
        self.assertTrue(other.image.storage.exists(other.image.name))

    def test_used_materials_and_private_piece_names_are_protected(self):
        piece = Piece.objects.create(owner=self.member, name='PIEZA PRIVADA', clay_material=self.personal)
        for primary in [True, False]:
            if not primary:
                piece.clay_material = None
                piece.save()
                GlazeUse.objects.create(piece=piece, glaze=self.personal, layers=2)
            url = reverse('material_delete', args=[self.personal.pk])
            preview = self.client.get(url)
            self.assertTrue(preview.context['blocked'])
            self.assertNotContains(preview, piece.name)
            self.assertNotContains(preview, 'type="submit"')
            self.assertEqual(self.client.post(url, {'confirm_delete': 'yes'}).status_code, 409)
            self.assertTrue(Glaze.objects.filter(pk=self.personal.pk).exists())
            self.assertTrue(Piece.objects.filter(pk=piece.pk).exists())

    def test_recipe_references_protect_material_even_from_other_material_uses(self):
        version = RecipeVersion.objects.create(glaze=self.personal, number=1)
        piece = Piece.objects.create(owner=self.member, name='Privada')
        use = GlazeUse.objects.create(piece=piece, glaze=self.group_material, recipe_version=version)
        response = self.client.post(reverse('material_delete', args=[self.personal.pk]), {'confirm_delete': 'yes'})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(RecipeVersion.objects.filter(pk=version.pk).exists())
        self.assertTrue(GlazeUse.objects.filter(pk=use.pk).exists())

    def test_rollback_keeps_records_and_photo_files(self):
        photo = save_photos([image_file()], glaze=self.personal)[0]
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaises(ValueError):
                with transaction.atomic():
                    delete_material(self.personal)
                    raise ValueError('rollback')
        self.assertTrue(Glaze.objects.filter(pk=self.personal.pk).exists())
        self.assertTrue(Photo.objects.filter(pk=photo.pk).exists())
        self.assertTrue(photo.image.storage.exists(photo.image.name))
