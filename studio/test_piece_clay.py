import importlib
from types import SimpleNamespace
from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from .forms import PieceForm
from .models import Circle, Gallery, GalleryEntry, Glaze, GlazeUse, Piece, User


@override_settings(LANGUAGE_CODE='es', SECURE_SSL_REDIRECT=False)
class PieceClayTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.owner = User.objects.create_user('clay-owner')
        self.member = User.objects.create_user('clay-member')
        self.stranger = User.objects.create_user('clay-stranger')
        self.workshop = Circle.objects.create(owner=self.owner, name='Taller barro')
        self.workshop.members.add(self.owner, self.member)
        self.personal = Glaze.objects.create(owner=self.owner, name='Pasta privada', material_type='clay')
        self.shared = Glaze.objects.create(owner=self.owner, group=self.workshop, name='Gres del taller', material_type='clay')
        self.other = Glaze.objects.create(owner=self.stranger, name='Barro ajeno', material_type='clay')
        self.glaze = Glaze.objects.create(owner=self.owner, name='Esmalte', material_type='glaze')
        self.engobe = Glaze.objects.create(owner=self.owner, name='Engobe', material_type='engobe')
        self.client.force_login(self.owner)

    def payload(self, **extra):
        return {'name':'Nueva pieza', 'stage':'raw', 'started_on':'2026-10-27', **extra}

    def test_selector_contains_only_accessible_clays_not_other_material_types(self):
        form = PieceForm(user=self.owner)
        self.assertEqual(set(form.fields['clay_material'].queryset), {self.personal,self.shared})
        self.assertNotIn('clay', form.fields)
        member_form = PieceForm(user=self.member)
        self.assertEqual(set(member_form.fields['clay_material'].queryset), {self.shared})
        response = self.client.get(reverse('piece_new'))
        self.assertContains(response, 'name="clay_material"')
        self.assertNotContains(response, 'name="clay"')

    def test_creation_saves_a_real_material_reference_and_related_piece(self):
        response = self.client.post(reverse('piece_new'), self.payload(clay_material=self.shared.pk))
        self.assertEqual(response.status_code,302)
        piece = Piece.objects.get(name='Nueva pieza')
        self.assertEqual(piece.clay_material_id,self.shared.pk)
        self.assertEqual(piece.clay,self.shared.name)
        self.assertContains(self.client.get(reverse('glaze',args=[self.shared.pk])),piece.name)
        self.shared.name = 'Gres renombrado'
        self.shared.save()
        self.assertContains(self.client.get(reverse('piece',args=[piece.pk])), 'Gres renombrado')
        self.assertContains(self.client.get(reverse('pieces'), {'q':'renombrado'}), piece.name)

    def test_wrong_type_private_id_and_free_text_are_rejected(self):
        for value in [self.glaze.pk,self.engobe.pk,self.other.pk,'Un barro escrito']:
            response = self.client.post(reverse('piece_new'),self.payload(clay_material=value))
            self.assertEqual(response.status_code,200)
            self.assertIn('clay_material',response.context['form'].errors)
        self.assertFalse(Piece.objects.filter(owner=self.owner).exists())

    def test_legacy_text_survives_until_the_owner_chooses_a_material(self):
        piece = Piece.objects.create(owner=self.owner,name='Anterior',clay='Barro de una pieza antigua')
        response = self.client.get(reverse('piece_edit',args=[piece.pk]))
        self.assertContains(response,'Barro de una pieza antigua')
        self.client.post(reverse('piece_edit',args=[piece.pk]),self.payload(clay_material=''))
        piece.refresh_from_db()
        self.assertEqual(piece.clay,'Barro de una pieza antigua')
        self.assertIsNone(piece.clay_material_id)
        self.client.post(reverse('piece_edit',args=[piece.pk]),self.payload(clay_material=self.personal.pk))
        piece.refresh_from_db()
        self.assertEqual(piece.clay_material_id,self.personal.pk)

    def test_explicit_clear_and_omitted_field_have_different_meanings(self):
        piece = Piece.objects.create(owner=self.owner,name='Base',clay=self.personal.name,clay_material=self.personal)
        self.client.post(reverse('piece_edit',args=[piece.pk]),self.payload())
        piece.refresh_from_db()
        self.assertEqual(piece.clay_material_id,self.personal.pk)
        self.client.post(reverse('piece_edit',args=[piece.pk]),self.payload(clay_material=''))
        piece.refresh_from_db()
        self.assertIsNone(piece.clay_material_id)
        self.assertEqual(piece.clay,'')

    def test_private_clay_is_redacted_in_shared_piece_list_and_gallery(self):
        piece = Piece.objects.create(owner=self.owner,name='Pieza compartida',clay=self.personal.name,clay_material=self.personal)
        piece.shared_groups.add(self.workshop)
        gallery = Gallery.objects.create(owner=self.owner,workshop=self.workshop,name='Colección',audience='group')
        GalleryEntry.objects.create(gallery=gallery,piece=piece,title=piece.name)
        self.client.force_login(self.member)
        for url, query in [(reverse('piece',args=[piece.pk]),{}),(reverse('pieces'),{'scope':'shared'}),(reverse('gallery_manage',args=[gallery.pk]),{})]:
            response = self.client.get(url,query)
            self.assertContains(response,'Material privado')
            self.assertNotContains(response,self.personal.name)
        self.assertEqual(self.client.get(reverse('glaze',args=[self.personal.pk])).status_code,404)
        response = self.client.get(reverse('pieces'),{'scope':'shared','q':self.personal.name})
        self.assertEqual(response.context['page'].paginator.count,0)

    def test_revoked_material_link_is_preserved_without_exposing_its_name(self):
        piece = Piece.objects.create(owner=self.member,name='Con barro del taller',clay=self.shared.name,clay_material=self.shared)
        self.workshop.members.remove(self.member)
        self.client.force_login(self.member)
        response = self.client.get(reverse('piece_edit',args=[piece.pk]))
        self.assertNotContains(response,self.shared.name)
        self.assertContains(response,'Material no disponible')
        response = self.client.post(reverse('piece_edit',args=[piece.pk]),self.payload(clay_material=self.shared.pk))
        self.assertEqual(response.status_code,302)
        piece.refresh_from_db()
        self.assertEqual(piece.clay_material_id,self.shared.pk)

    def test_migration_links_only_unambiguous_existing_clay_uses(self):
        linked = Piece.objects.create(owner=self.owner,name='Coincide',clay=self.personal.name)
        GlazeUse.objects.create(piece=linked,glaze=self.personal)
        unmatched = Piece.objects.create(owner=self.owner,name='Texto distinto',clay='Gres desconocido')
        ambiguous = Piece.objects.create(owner=self.owner,name='Mezcla',clay=self.personal.name)
        GlazeUse.objects.create(piece=ambiguous,glaze=self.personal)
        GlazeUse.objects.create(piece=ambiguous,glaze=self.shared)
        migration = importlib.import_module('studio.migrations.0012_piece_clay_material')
        migration.link_existing_clay_uses(apps,SimpleNamespace(connection=connection))
        for piece in [linked,unmatched,ambiguous]:
            piece.refresh_from_db()
        self.assertEqual(linked.clay_material_id,self.personal.pk)
        self.assertIsNone(unmatched.clay_material_id)
        self.assertIsNone(ambiguous.clay_material_id)
        self.assertEqual(unmatched.clay,'Gres desconocido')
