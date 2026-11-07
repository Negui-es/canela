from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .forms import GlazeUseForm, PieceForm
from .models import Circle, Glaze, GlazeUse, Mold, Piece, User
from .permissions import can_read


@override_settings(SECURE_SSL_REDIRECT=False)
class MaterialRetirementTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.admin = User.objects.create_user('retirement-admin')
        self.member = User.objects.create_user('retirement-member')
        self.workshop = Circle.objects.create(owner=self.admin, name='Taller')
        self.workshop.members.add(self.member)
        self.materials = [Glaze.objects.create(owner=self.admin, group=self.workshop, name='Material ' + category, material_type=category) for category in Glaze.MaterialType.values]
        self.materials.append(Mold.objects.create(owner=self.admin, group=self.workshop, name='Material molde'))
        self.client.force_login(self.admin)

    def retire_url(self, material):
        return reverse('mold_retire' if isinstance(material, Mold) else 'material_retire', args=[material.pk])

    def list_url(self, material):
        return reverse('molds' if isinstance(material, Mold) else 'glazes')

    def params(self, material, **extra):
        return {**({} if isinstance(material, Mold) else {'material_type': material.material_type}), **extra}

    def test_retirement_hides_all_four_types_from_catalog_search_and_new_piece_choices(self):
        for material in self.materials:
            self.assertEqual(self.client.post(self.retire_url(material), {'action': 'retire'}).status_code, 302)
            material.refresh_from_db()
            self.assertTrue(material.is_retired)
            self.assertTrue(can_read(material, self.member))
            for params in [self.params(material), self.params(material, q=material.name)]:
                response = self.client.get(self.list_url(material), params, HTTP_HX_REQUEST='true')
                self.assertNotContains(response, material.name)
                self.assertEqual(response.context['page'].paginator.count, 0)
        form = PieceForm(user=self.member)
        self.assertFalse(form.fields['glazes'].queryset.exists())
        self.assertFalse(form.fields['clay_material'].queryset.exists())
        self.assertFalse(form.fields['mold'].queryset.exists())
        self.assertFalse(GlazeUseForm(user=self.member).fields['glaze'].queryset.exists())

    def test_historical_links_survive_retirement_and_piece_edits(self):
        clay = next(material for material in self.materials if getattr(material, 'material_type', '') == 'clay')
        mold = self.materials[-1]
        piece = Piece.objects.create(owner=self.member, name='Pieza histórica', clay_material=clay, mold=mold)
        uses = [GlazeUse.objects.create(piece=piece, glaze=material, layers=2) for material in self.materials if isinstance(material, Glaze)]
        for material in self.materials:
            self.client.post(self.retire_url(material), {'action': 'retire'})
        self.client.force_login(self.member)
        response = self.client.get(reverse('piece_edit', args=[piece.pk]))
        self.assertContains(response, clay.name)
        self.assertContains(response, mold.name)
        self.assertContains(response, 'Retirado')
        payload = {'name': piece.name, 'started_on': '2026-10-28', 'stage': 'raw', 'clay_material': clay.pk, 'mold': mold.pk, 'glazes_present': '1'}
        self.assertEqual(self.client.post(reverse('piece_edit', args=[piece.pk]), payload).status_code, 302)
        piece.refresh_from_db()
        self.assertEqual(piece.clay_material, clay)
        self.assertEqual(piece.mold, mold)
        self.assertEqual(piece.glaze_uses.count(), len(uses))
        form = GlazeUseForm(user=self.member, instance=uses[0])
        self.assertIn(uses[0].glaze, form.fields['glaze'].queryset)
        with self.assertRaises(ProtectedError):
            mold.delete()

    def test_retired_view_is_management_only_and_restore_makes_material_available_again(self):
        for material in self.materials:
            self.client.force_login(self.admin)
            self.client.post(self.retire_url(material), {'action': 'retire'})
            response = self.client.get(self.list_url(material), self.params(material, retired='1', q=material.name), HTTP_HX_REQUEST='true')
            self.assertContains(response, material.name)
            self.client.force_login(self.member)
            response = self.client.get(self.list_url(material), self.params(material, retired='1', q=material.name))
            self.assertEqual(response.context['page'].paginator.count, 0)
            self.assertEqual(self.client.post(self.retire_url(material), {'action': 'restore'}).status_code, 404)
            self.client.force_login(self.admin)
            self.assertEqual(self.client.post(self.retire_url(material), {'action': 'restore'}).status_code, 302)
            material.refresh_from_db()
            self.assertFalse(material.is_retired)
            self.assertContains(self.client.get(self.list_url(material), self.params(material)), material.name)

    def test_unused_retired_records_can_be_deleted_but_used_ones_are_protected(self):
        for material in self.materials:
            self.client.post(self.retire_url(material), {'action': 'retire'})
            piece = Piece.objects.create(owner=self.member, name='Uso')
            if isinstance(material, Mold):
                piece.mold = material
                piece.save()
                url = reverse('mold_delete', args=[material.pk])
            else:
                GlazeUse.objects.create(piece=piece, glaze=material)
                url = reverse('material_delete', args=[material.pk])
            self.assertEqual(self.client.post(url, {'confirm_delete': 'yes'}).status_code, 409)
            piece.delete()
            self.assertEqual(self.client.post(url, {'confirm_delete': 'yes'}).status_code, 302)
            self.assertFalse(type(material).objects.filter(pk=material.pk).exists())

    def test_personal_owner_can_retire_but_members_cannot_retire_workshop_items(self):
        self.client.force_login(self.member)
        for material in self.materials:
            self.assertEqual(self.client.post(self.retire_url(material), {'action': 'retire'}).status_code, 404)
            material.refresh_from_db()
            self.assertFalse(material.is_retired)
        for model in [Glaze, Mold]:
            personal = model.objects.create(owner=self.member, name='Personal')
            self.assertEqual(self.client.post(self.retire_url(personal), {'action': 'retire'}).status_code, 302)
            personal.refresh_from_db()
            self.assertTrue(personal.is_retired)

    def test_retirement_requires_post_csrf_and_valid_action(self):
        url = self.retire_url(self.materials[0])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'action': 'invalid'}).status_code, 400)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url, {'action': 'retire'}).status_code, 403)
        self.materials[0].refresh_from_db()
        self.assertFalse(self.materials[0].is_retired)

    def test_all_unavailable_reasons_hide_each_type_and_can_be_changed_or_restored(self):
        for material in self.materials:
            for reason in ['out_of_stock', 'retired', 'unavailable']:
                response = self.client.post(self.retire_url(material), {'availability': reason})
                self.assertEqual(response.status_code, 302)
                material.refresh_from_db()
                self.assertEqual(material.availability, reason)
                self.assertFalse(material.is_available)
                response = self.client.get(self.list_url(material), self.params(material, q=material.name), HTTP_HX_REQUEST='true')
                self.assertEqual(response.context['page'].paginator.count, 0)
                self.assertNotContains(response, material.name)
                response = self.client.get(self.list_url(material), self.params(material, unavailable='1', q=material.name))
                self.assertEqual(response.context['page'].paginator.count, 1)
            self.client.post(self.retire_url(material), {'availability': 'available'})
            material.refresh_from_db()
            self.assertTrue(material.is_available)
            response = self.client.get(self.list_url(material), self.params(material, q=material.name))
            self.assertEqual(response.context['page'].paginator.count, 1)

    def test_out_of_stock_keeps_primary_piece_link_and_new_reason_is_visible(self):
        clay = next(material for material in self.materials if getattr(material, 'material_type', '') == 'clay')
        piece = Piece.objects.create(owner=self.member, name='Pieza con barro agotado', clay_material=clay)
        self.client.post(self.retire_url(clay), {'availability': 'out_of_stock'})
        self.client.force_login(self.member)
        response = self.client.get(reverse('piece_edit', args=[piece.pk]))
        self.assertContains(response, clay.name)
        self.assertContains(response, 'Agotado')
        piece.refresh_from_db()
        self.assertEqual(piece.clay_material_id, clay.pk)


class MaterialAvailabilityMigrationTests(TransactionTestCase):
    def test_previous_retirement_flags_and_mold_states_keep_their_meaning(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        original_targets = executor.loader.graph.leaf_nodes()
        previous = [('studio', '0014_material_retirement')]
        current = [('studio', '0015_material_availability')]
        try:
            executor.migrate(previous)
            old = executor.loader.project_state(previous).apps
            user = old.get_model('studio', 'User').objects.create(username='availability-migration')
            glaze = old.get_model('studio', 'Glaze').objects.create(owner_id=user.pk, name='Retirado', is_retired=True)
            retired = old.get_model('studio', 'Mold').objects.create(owner_id=user.pk, name='Retirado', state='retired')
            damaged = old.get_model('studio', 'Mold').objects.create(owner_id=user.pk, name='Deteriorado', state='damaged')
            executor = MigrationExecutor(connection)
            executor.migrate(current)
            new = executor.loader.project_state(current).apps
            self.assertEqual(new.get_model('studio', 'Glaze').objects.get(pk=glaze.pk).availability, 'retired')
            self.assertEqual(new.get_model('studio', 'Mold').objects.get(pk=retired.pk).availability, 'retired')
            self.assertEqual(new.get_model('studio', 'Mold').objects.get(pk=damaged.pk).availability, 'unavailable')
            self.assertEqual(new.get_model('studio', 'Mold').objects.get(pk=damaged.pk).state, 'damaged')
        finally:
            MigrationExecutor(connection).migrate(original_targets)
