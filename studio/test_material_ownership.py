from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib import admin
from django.http import QueryDict
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .forms import GlazeForm, PieceForm
from .library import materials_for
from .models import Circle, Glaze, GlazeUse, Piece, User
from .permissions import can_read
from .services import save_photos
from .tests import image_file


@override_settings(SECURE_SSL_REDIRECT=False)
class MaterialOwnershipTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        temporary = TemporaryDirectory(dir=settings.BASE_DIR / 'data')
        self.addCleanup(temporary.cleanup)
        storage = override_settings(MEDIA_ROOT=temporary.name)
        storage.enable()
        self.addCleanup(storage.disable)
        self.administrator = User.objects.create_user('materials-administrator')
        self.member = User.objects.create_user('materials-member')
        self.workshop = Circle.objects.create(owner=self.administrator, name='Taller')
        self.workshop.members.add(self.member)
        self.personal = Glaze.objects.create(owner=self.member, name='Material privado', material_type='clay')
        self.catalog = Glaze.objects.create(owner=self.administrator, group=self.workshop, name='Material del taller', material_type='clay')

    def test_no_sharing_control_and_only_managed_workshops_can_be_selected(self):
        for user in [self.administrator, self.member]:
            form = GlazeForm(user=user)
            self.assertNotIn('shared_groups', form.fields)
            self.client.force_login(user)
            response = self.client.get(reverse('glaze_new'))
            self.assertNotContains(response, 'name="shared_groups"')
            self.assertNotContains(response, 'data-personal-sharing')
        self.assertFalse(GlazeForm(user=self.member).fields['group'].queryset.exists())
        self.assertIn(self.workshop, GlazeForm(user=self.administrator).fields['group'].queryset)

    def test_legacy_sharing_does_not_grant_access_to_catalog_picker_or_photos(self):
        self.personal.shared_groups.add(self.workshop)
        photo = save_photos([image_file()], glaze=self.personal)[0]
        self.assertFalse(can_read(self.personal, self.administrator))
        self.assertNotIn(self.personal, materials_for(self.administrator))
        self.assertNotIn(self.personal, materials_for(self.administrator, self.workshop.pk))
        self.assertNotIn(self.personal, PieceForm(user=self.administrator).fields['clay_material'].queryset)
        self.client.force_login(self.administrator)
        for name, identifier in [('glaze', self.personal.pk), ('photo', photo.pk)]:
            self.assertEqual(self.client.get(reverse(name, args=[identifier])).status_code, 404)
        self.assertTrue(can_read(self.personal, self.member))
        self.assertIn(self.catalog, materials_for(self.member))

    def test_forged_sharing_is_rejected_even_for_an_administrator(self):
        self.client.force_login(self.administrator)
        payload = QueryDict(mutable=True)
        payload.update({'name': 'No compartir', 'kind': 'commercial', 'material_type': 'clay'})
        payload.setlist('shared_groups', [str(self.workshop.pk), ''])
        response = self.client.post(reverse('glaze_new'), payload.urlencode(), content_type='application/x-www-form-urlencoded')
        form = GlazeForm(data=payload, user=self.administrator)
        self.assertFalse(form.is_valid())
        self.assertIn('__all__', form.errors)
        self.assertFalse(Glaze.objects.filter(name='No compartir').exists())
        self.assertEqual(response.status_code, 200)

    def test_only_admin_can_create_workshop_material_and_personal_references_remain(self):
        piece = Piece.objects.create(owner=self.member, name='Pieza', clay_material=self.personal)
        use = GlazeUse.objects.create(piece=piece, glaze=self.personal)
        payload = {'name': 'Nuevo del taller', 'kind': 'commercial', 'material_type': 'clay', 'group': self.workshop.pk}
        self.client.force_login(self.member)
        self.assertEqual(self.client.post(reverse('glaze_new'), payload).status_code, 200)
        self.assertFalse(Glaze.objects.filter(name=payload['name']).exists())
        self.client.force_login(self.administrator)
        self.assertEqual(self.client.post(reverse('glaze_new'), payload).status_code, 302)
        material = Glaze.objects.get(name=payload['name'])
        self.assertEqual(material.group, self.workshop)
        self.assertTrue(can_read(material, self.member))
        piece.refresh_from_db()
        self.assertEqual(piece.clay_material, self.personal)
        self.assertTrue(GlazeUse.objects.filter(pk=use.pk).exists())

    def test_admin_site_also_has_no_sharing_and_no_unmanaged_workshops(self):
        model_admin = admin.site._registry[Glaze]
        request = RequestFactory().get('/admin/')
        request.user = self.member
        self.assertIn('shared_groups', model_admin.exclude)
        field = model_admin.formfield_for_foreignkey(Glaze._meta.get_field('group'), request)
        self.assertFalse(field.queryset.exists())
        request.user = self.administrator
        field = model_admin.formfield_for_foreignkey(Glaze._meta.get_field('group'), request)
        self.assertIn(self.workshop, field.queryset)
