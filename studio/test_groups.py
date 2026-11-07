from tempfile import TemporaryDirectory
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .forms import PieceForm
from .models import Circle, Gallery, Glaze, Invitation, Piece, RecipeVersion, User
from .permissions import can_edit, can_read, can_read_gallery, group_access, visible


@override_settings(LANGUAGE_CODE='es')
class GroupHierarchyTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.owner = User.objects.create_user('workshop-owner')
        self.admin = User.objects.create_user('second-admin')
        self.teacher = User.objects.create_user('monday-teacher')
        self.student = User.objects.create_user('monday-student')
        self.tuesday_user = User.objects.create_user('tuesday-student')
        self.outsider = User.objects.create_user('outside')
        self.root = Circle.objects.create(owner=self.owner, name='Taller Serendipia')
        self.root.members.add(self.owner, self.admin)
        self.root.administrators.add(self.owner, self.admin)
        self.monday = Circle.objects.create(owner=self.teacher, parent=self.root, name='Clase lunes')
        self.monday.members.add(self.teacher, self.student)
        self.tuesday = Circle.objects.create(owner=self.owner, parent=self.root, name='Clase martes')
        self.tuesday.members.add(self.tuesday_user)
        self.nested = Circle.objects.create(owner=self.teacher, parent=self.monday, name='Lunes avanzado')
        self.general = Glaze.objects.create(owner=self.admin, group=self.root, name='Barro general', material_type='clay')
        self.local = Glaze.objects.create(owner=self.teacher, group=self.monday, name='Engobe lunes', material_type='engobe')
        self.other = Glaze.objects.create(owner=self.owner, group=self.tuesday, name='Esmalte martes')
        self.client.force_login(self.owner)

    def test_member_reads_upwards_but_never_sideways_or_downwards(self):
        self.assertTrue(can_read(self.general, self.student))
        self.assertTrue(can_read(self.local, self.student))
        self.assertFalse(can_read(self.other, self.student))
        deep = Glaze.objects.create(owner=self.teacher, group=self.nested, name='Solo avanzado')
        self.assertFalse(can_read(deep, self.student))
        self.nested.members.add(self.outsider)
        for material in [self.general, self.local, deep]:
            self.assertTrue(can_read(material, self.outsider))
        self.assertFalse(can_read(self.other, self.outsider))
        self.assertFalse(self.root.members.filter(pk=self.student.pk).exists())
        self.client.force_login(self.student)
        for material in [self.general, self.local]:
            self.assertContains(self.client.get(reverse('glazes'), {'origin': self.monday.pk, 'material_type': material.material_type}), material.name)
            self.assertContains(self.client.get(reverse('glazes'), {'material_type': material.material_type}), material.name)
            self.assertEqual(self.client.get(reverse('glaze', args=[material.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('glaze', args=[self.other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('circle', args=[self.tuesday.pk])).status_code, 404)
        groups = self.client.get(reverse('circles'))
        self.assertContains(groups, self.root.name)
        self.assertContains(groups, self.monday.name)
        self.assertNotContains(groups, self.tuesday.name)
        parent_page = self.client.get(reverse('circle', args=[self.root.pk]))
        self.assertNotContains(parent_page, self.admin.username)
        self.assertNotContains(parent_page, self.tuesday.name)

    def test_pieces_and_galleries_inherit_only_explicit_sharing(self):
        general_piece = Piece.objects.create(owner=self.owner, name='General')
        general_piece.shared_groups.add(self.root)
        monday_piece = Piece.objects.create(owner=self.teacher, name='Clase')
        monday_piece.shared_groups.add(self.monday)
        tuesday_piece = Piece.objects.create(owner=self.owner, name='Otra clase')
        tuesday_piece.shared_groups.add(self.tuesday)
        private = Piece.objects.create(owner=self.teacher, name='Privado')
        for piece in [general_piece, monday_piece]:
            self.assertTrue(can_read(piece, self.student))
        for piece in [tuesday_piece, private]:
            self.assertFalse(can_read(piece, self.student))
        self.assertFalse(can_read(private, self.admin))
        gallery = Gallery.objects.create(owner=self.owner, name='General', audience='group')
        gallery.shared_groups.add(self.root)
        self.assertTrue(can_read_gallery(gallery, self.student))
        self.client.force_login(self.student)
        self.assertContains(self.client.get(reverse('workshop_galleries', args=[self.monday.pk]), follow=True), 'General')
        self.assertContains(self.client.get(reverse('galleries')), 'General')

    def test_administration_inherits_downwards_and_personal_shares_stay_read_only(self):
        self.assertTrue(can_edit(self.general, self.admin))
        self.assertTrue(can_edit(self.local, self.admin))
        self.assertTrue(can_edit(self.local, self.teacher))
        self.assertFalse(can_edit(self.general, self.teacher))
        self.assertFalse(can_edit(self.local, self.student))
        personal = Glaze.objects.create(owner=self.student, name='Personal compartido')
        personal.shared_groups.add(self.monday)
        self.assertFalse(can_read(personal, self.admin))
        self.assertFalse(can_edit(personal, self.admin))
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('glaze_edit', args=[self.general.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('circle_edit', args=[self.root.pk])).status_code, 404)
        self.client.force_login(self.admin)
        for name in ['glaze_edit', 'recipe_add', 'sample_add']:
            self.assertEqual(self.client.get(reverse(name, args=[self.local.pk])).status_code, 200)

    def test_admin_can_create_and_edit_group_material_without_taking_ownership(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('glaze_new'), {
            'name': 'Del taller', 'kind': 'commercial', 'material_type': 'glaze', 'group': self.root.pk,
        })
        self.assertEqual(response.status_code, 302)
        material = Glaze.objects.get(name='Del taller')
        self.assertEqual(material.group_id, self.root.pk)
        self.assertFalse(material.shared_groups.exists())
        version = RecipeVersion.objects.create(glaze=self.local, number=1)
        creator = self.local.owner_id
        response = self.client.post(reverse('glaze_edit', args=[self.local.pk]), {
            'name': 'Actualizado', 'kind': 'recipe', 'material_type': 'engobe', 'group': '',
        })
        self.assertEqual(response.status_code, 302)
        self.local.refresh_from_db()
        self.assertEqual(self.local.owner_id, creator)
        self.assertEqual(self.local.group_id, self.monday.pk)
        self.assertEqual(self.local.latest_recipe.pk, version.pk)

    def test_ordinary_members_cannot_publish_upwards_or_create_group_materials(self):
        form = PieceForm(user=self.student)
        self.assertIn(self.monday, form.fields['shared_groups'].queryset)
        self.assertNotIn(self.root, form.fields['shared_groups'].queryset)
        self.client.force_login(self.student)
        response = self.client.post(reverse('glaze_new'), {'name': 'No permitido', 'kind': 'commercial', 'material_type': 'clay', 'group': self.root.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('group', response.context['form'].errors)
        self.assertFalse(Glaze.objects.filter(name='No permitido').exists())
        self.assertEqual(self.client.get(reverse('circle_new'), {'parent': self.root.pk}).status_code, 404)

    def test_role_management_and_last_admin_protection(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('circle_role', args=[self.root.pk, self.owner.pk]), {'role': 'member'})
        self.assertEqual(response.status_code, 302)
        self.root.refresh_from_db()
        self.assertEqual(self.root.owner_id, self.admin.pk)
        self.assertNotIn(self.root.pk, group_access(self.owner)[1])
        self.assertEqual(self.client.post(reverse('circle_role', args=[self.root.pk, self.admin.pk]), {'role': 'member'}).status_code, 400)
        self.assertEqual(self.client.post(reverse('circle_remove', args=[self.root.pk, self.admin.pk])).status_code, 400)
        self.client.force_login(self.student)
        self.assertEqual(self.client.post(reverse('circle_role', args=[self.monday.pk, self.student.pk]), {'role': 'admin'}).status_code, 403)

    def test_subgroup_creation_and_editing(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('circle_new'), {'name': 'Clase miércoles', 'parent': self.root.pk})
        self.assertEqual(response.status_code, 302)
        child = Circle.objects.get(name='Clase miércoles')
        self.assertEqual(child.parent_id, self.root.pk)
        self.assertTrue(child.administrators.filter(pk=self.admin.pk).exists())
        response = self.client.post(reverse('circle_edit', args=[child.pk]), {'name': 'Miércoles tarde', 'parent': self.tuesday.pk})
        self.assertEqual(response.status_code, 302)
        child.refresh_from_db()
        self.assertEqual(child.parent_id, self.tuesday.pk)
        self.assertEqual(child.name, 'Miércoles tarde')
        self.root.parent = self.nested
        with self.assertRaises(ValidationError):
            self.root.full_clean()

    def test_only_parent_admin_can_move_a_class_and_cycles_are_rejected(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('circle_edit', args=[self.monday.pk]), {'name': 'Lunes', 'parent': ''})
        self.assertEqual(response.status_code, 302)
        self.monday.refresh_from_db()
        self.assertEqual(self.monday.parent_id, self.root.pk)
        self.client.force_login(self.admin)
        response = self.client.post(reverse('circle_edit', args=[self.root.pk]), {'name': self.root.name, 'parent': self.nested.pk})
        self.assertEqual(response.status_code, 200)
        self.assertIn('parent', response.context['form'].errors)

    def test_reparenting_updates_inherited_access_immediately(self):
        other_workshop = Circle.objects.create(owner=self.admin, name='Otro taller')
        other_material = Glaze.objects.create(owner=self.admin, group=other_workshop, name='Otro material general')
        self.client.force_login(self.admin)
        response = self.client.post(reverse('circle_edit', args=[self.monday.pk]), {'name': self.monday.name, 'parent': other_workshop.pk})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(can_read(self.general, self.student))
        self.assertTrue(can_read(other_material, self.student))
        self.assertTrue(can_read(self.local, self.student))

    def test_departure_revokes_access_but_keeps_material_and_history(self):
        self.nested.owner = self.admin
        self.nested.save(update_fields=['owner'])
        self.monday.administrators.add(self.admin)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('circle_remove', args=[self.monday.pk, self.teacher.pk])).status_code, 302)
        self.local.refresh_from_db()
        self.assertFalse(can_read(self.local, self.teacher))
        self.assertTrue(can_read(self.local, self.student))
        self.assertFalse(can_edit(self.local, self.teacher))
        self.monday.members.remove(self.student)
        self.assertFalse(can_read(self.general, self.student))
        self.assertFalse(can_read(self.local, self.student))
        self.assertNotIn(self.general, visible(Glaze.objects.all(), self.student))

    def test_material_survives_creator_account_deletion(self):
        material = Glaze.objects.create(owner=self.outsider, group=self.root, name='Conservar')
        version = RecipeVersion.objects.create(glaze=material, number=1)
        self.outsider.delete()
        material.refresh_from_db()
        self.assertIsNone(material.owner_id)
        self.assertEqual(material.latest_recipe.pk, version.pk)
        self.assertTrue(can_read(material, self.student))

    @override_settings(ALLOW_NEW_ACCOUNTS=True)
    def test_admin_invites_to_child_without_parent_membership(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('invite'), {'circle': self.monday.pk})
        self.assertEqual(response.status_code, 302)
        invitation = Invitation.objects.get(circle=self.monday, created_by=self.admin)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.post(reverse('accept_invite', args=[invitation.pk])).status_code, 302)
        self.assertTrue(self.monday.members.filter(pk=self.outsider.pk).exists())
        self.assertFalse(self.root.members.filter(pk=self.outsider.pk).exists())
        self.assertTrue(can_read(self.general, self.outsider))
        self.assertFalse(can_read(self.other, self.outsider))

    def test_group_photos_follow_inherited_visibility_and_admin_permissions(self):
        from .tests import image_file
        from .services import save_photos
        with TemporaryDirectory(dir='data') as media, override_settings(MEDIA_ROOT=media):
            photo = save_photos([image_file()], glaze=self.general)[0]
            self.client.force_login(self.student)
            response = self.client.get(reverse('photo', args=[photo.pk]))
            self.assertEqual(response.status_code, 200)
            response.close()
            self.assertEqual(self.client.get(reverse('photos_manage', args=['glaze', self.general.pk])).status_code, 404)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse('photos_manage', args=['glaze', self.general.pk])).status_code, 200)
            response = self.client.post(reverse('sample_add', args=[self.general.pk]), {'date': '2026-10-27', 'temperature': '1240', 'shrinkage': '12'})
            self.assertEqual(response.status_code, 302)
            sample = self.general.samples.get()
            self.assertEqual(self.client.get(reverse('photos_manage', args=['sample', sample.pk])).status_code, 200)
            self.monday.members.remove(self.student)
            self.client.force_login(self.student)
            self.assertEqual(self.client.get(reverse('photo', args=[photo.pk])).status_code, 404)

    def test_upgrade_preserves_existing_owner_and_personal_materials(self):
        import importlib
        from django.apps import apps
        from django.db import connection
        legacy = Circle.objects.create(owner=self.outsider, name='Grupo anterior')
        personal = Glaze.objects.create(owner=self.outsider, name='Material anterior')
        migration = importlib.import_module('studio.migrations.0009_circle_administrators_circle_parent_glaze_group_and_more')
        from types import SimpleNamespace
        migration.preserve_group_owners(apps, SimpleNamespace(connection=connection))
        self.assertTrue(legacy.members.filter(pk=self.outsider.pk).exists())
        self.assertTrue(legacy.administrators.filter(pk=self.outsider.pk).exists())
        personal.refresh_from_db()
        self.assertIsNone(personal.group_id)
        self.assertEqual(personal.owner_id, self.outsider.pk)
