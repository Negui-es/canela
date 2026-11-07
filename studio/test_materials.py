from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from .models import Circle, Glaze, GlazeUse, Piece, RecipeVersion, User
from .forms import GlazeForm, SampleForm


@override_settings(LANGUAGE_CODE='es')
class MaterialTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.owner = User.objects.create_user('material-owner')
        self.other = User.objects.create_user('material-other')
        self.client.force_login(self.owner)

    def test_create_all_material_types_and_link_them_to_a_piece(self):
        materials = []
        for category in Glaze.MaterialType.values:
            response = self.client.post(reverse('glaze_new'), {
                'name': f'Material {category}', 'material_type': category,
                'kind': 'recipe', 'temperature': '1200 °C',
            })
            self.assertEqual(response.status_code, 302)
            material = Glaze.objects.get(name=f'Material {category}')
            self.assertEqual(material.material_type, category)
            RecipeVersion.objects.create(glaze=material, number=1)
            materials.append(material)
        response = self.client.post(reverse('piece_new'), {
            'name': 'Pieza con tres materiales', 'started_on': '2026-10-27',
            'stage': 'raw', 'glazes_present': '1',
            'glazes': [material.pk for material in materials],
        })
        self.assertEqual(response.status_code, 302)
        piece = Piece.objects.get(name='Pieza con tres materiales')
        self.assertEqual(piece.glaze_uses.count(), 3)
        for use in piece.glaze_uses.all():
            self.assertEqual(use.recipe_version.number, 1)
            detail = self.client.get(reverse('glaze', args=[use.glaze_id]))
            self.assertContains(detail, piece.name)
            self.assertContains(detail, use.glaze.get_material_type_display())
        detail = self.client.get(reverse('piece', args=[piece.pk]))
        for material in materials:
            self.assertContains(detail, reverse('glaze', args=[material.pk]))
        self.assertContains(detail, 'Materiales utilizados')

    def test_category_filter_combines_search_sharing_and_pagination(self):
        circle = Circle.objects.create(owner=self.other, name='Materiales del grupo')
        circle.members.add(self.owner)
        for index in range(19):
            material = Glaze.objects.create(owner=self.other, group=circle, name=f'Tierra {index}', material_type='clay')
        Glaze.objects.create(owner=self.other, name='Tierra secreta', material_type='clay')
        Glaze.objects.create(owner=self.owner, name='Tierra engobe', material_type='engobe')
        filters = {'q': 'Tierra', 'scope': 'shared', 'material_type': 'clay'}
        response = self.client.get(reverse('glazes'), filters, HTTP_HX_REQUEST='true')
        self.assertEqual(response.context['page'].paginator.count, 19)
        self.assertNotContains(response, 'Tierra secreta')
        self.assertNotContains(response, 'Tierra engobe')
        self.assertContains(response, 'material_type=clay')
        self.assertContains(response, 'page=2')
        self.assertEqual(self.client.get(reverse('glazes'), {'material_type': 'clay'}).context['page'].paginator.count, 19)
        self.assertEqual(self.client.get(reverse('glazes'), {'material_type': 'clay', 'origin': 'personal'}).context['page'].paginator.count, 0)

    def test_editing_material_category_preserves_recipe_and_piece_use(self):
        material = Glaze.objects.create(owner=self.owner, name='Engobe antiguo')
        version = RecipeVersion.objects.create(glaze=material, number=1)
        piece = Piece.objects.create(owner=self.owner, name='Cuenco')
        use = GlazeUse.objects.create(piece=piece, glaze=material, recipe_version=version, grams=25, layers=2)
        response = self.client.post(reverse('glaze_edit', args=[material.pk]), {
            'name': material.name, 'kind': 'recipe', 'material_type': 'engobe',
        })
        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        use.refresh_from_db()
        self.assertEqual(material.material_type, 'engobe')
        self.assertEqual(use.recipe_version_id, version.pk)
        self.assertEqual(use.grams, 25)
        self.assertEqual(use.layers, 2)
        response = self.client.post(reverse('glaze_edit', args=[material.pk]), {
            'name': material.name, 'kind': 'recipe',
        })
        self.assertEqual(response.status_code, 302)
        material.refresh_from_db()
        self.assertEqual(material.material_type, 'engobe')

    def test_private_materials_cannot_be_assigned_and_invalid_categories_are_rejected(self):
        hidden = Glaze.objects.create(owner=self.other, name='Barro privado', material_type='clay')
        response = self.client.post(reverse('piece_new'), {
            'name': 'No guardar', 'started_on': '2026-10-27', 'stage': 'raw',
            'glazes_present': '1', 'glazes': [hidden.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('glazes', response.context['form'].errors)
        self.assertFalse(Piece.objects.exists())
        response = self.client.post(reverse('glaze_new'), {
            'name': 'Inválido', 'kind': 'commercial', 'material_type': 'unknown',
        })
        self.assertIn('material_type', response.context['form'].errors)

    def test_each_material_saves_its_own_parameters_and_ignores_other_types(self):
        cases = [
            ('glaze', {'finish': 'Satinado', 'transparency': 'translucent', 'application': 'Inmersión', 'absorption': 'not-a-number'}),
            ('engobe', {'application_stage': 'Dureza de cuero', 'compatible_clays': 'Gres blanco', 'application': 'Pincel', 'transparency': 'invalid'}),
            ('clay', {'clay_body': 'Gres', 'grog_percentage': '25', 'grog_size': '0–0,5', 'shrinkage': '12.5', 'absorption': '0', 'measurement_temperature': '1240', 'working_methods': 'Torno', 'transparency': 'invalid'}),
        ]
        for category, values in cases:
            with self.subTest(category=category):
                response = self.client.post(reverse('glaze_new'), {
                    'name': category, 'material_type': category, 'kind': 'commercial',
                    'brand': 'Fabricante', 'color': 'Blanco', **values,
                })
                self.assertEqual(response.status_code, 302)
                obj = Glaze.objects.get(name=category)
                form = GlazeForm(instance=obj, user=self.owner)
                for field in GlazeForm.TYPE_FIELDS[category]:
                    self.assertFalse(form.fields[field].disabled)
                if category == 'clay':
                    self.assertEqual(obj.absorption, 0)
                    detail = self.client.get(reverse('glaze', args=[obj.pk]))
                    self.assertContains(detail, 'Contracción total')
                    self.assertNotContains(detail, 'Transparencia')
                    self.assertNotContains(detail, 'Acabado')
                elif category == 'engobe':
                    self.assertEqual(obj.transparency, '')
                    self.assertContains(self.client.get(reverse('glaze', args=[obj.pk])), 'Dureza de cuero')

    def test_clay_percentages_are_validated_and_require_reference_temperature(self):
        data = {'name': 'Gres', 'kind': 'commercial', 'material_type': 'clay', 'grog_percentage': '101'}
        form = GlazeForm(data, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('grog_percentage', form.errors)
        data.update(grog_percentage='0', absorption='0')
        form = GlazeForm(data, user=self.owner)
        self.assertFalse(form.is_valid())
        self.assertIn('measurement_temperature', form.errors)
        data['measurement_temperature'] = '1200'
        self.assertTrue(GlazeForm(data, user=self.owner).is_valid())

    def test_samples_follow_material_type(self):
        for category in Glaze.MaterialType.values:
            material = Glaze.objects.create(owner=self.owner, name=category, material_type=category)
            form = SampleForm(material=material)
            self.assertEqual('clay' in form.fields, category != 'clay')
            self.assertEqual('layers' in form.fields, category != 'clay')
            self.assertEqual('shrinkage' in form.fields, category == 'clay')
            self.assertEqual('application_stage' in form.fields, category == 'engobe')
            payload = {'date': '2026-10-27', 'temperature': '1240'}
            if category == 'clay':
                payload.update(shrinkage='11', absorption='0.5', layers='999', clay='Irrelevant')
            else:
                payload.update(clay='Gres blanco', layers='2', application_stage='Seco')
            response = self.client.post(reverse('sample_add', args=[material.pk]), payload)
            self.assertEqual(response.status_code, 302)
            sample = material.samples.get()
            if category == 'clay':
                self.assertIsNone(sample.layers)
                self.assertEqual(sample.clay, '')
                self.assertEqual(sample.shrinkage, 11)
            else:
                self.assertEqual(sample.layers, 2)

    def test_clay_uses_cannot_save_coating_layers(self):
        material = Glaze.objects.create(owner=self.owner, name='Pasta base', material_type='clay')
        piece = Piece.objects.create(owner=self.owner, name='Pieza')
        initial = self.client.get(reverse('glaze_use_add', args=[piece.pk]))
        self.assertContains(initial, str(material.pk))
        self.assertContains(initial, 'data-material-type="clay"')
        response = self.client.post(reverse('glaze_use_add', args=[piece.pk]), {
            'glaze': material.pk, 'grams': '500', 'layers': 'not-a-number', 'method': 'Torno',
        })
        self.assertEqual(response.status_code, 302)
        use = piece.glaze_uses.get()
        self.assertIsNone(use.layers)
        self.assertEqual(use.grams, 500)

    def test_material_choice_changes_fields_without_javascript_and_icons_differ(self):
        for category in Glaze.MaterialType.values:
            response = self.client.get(reverse('glaze_new'), {'material_type': category})
            self.assertEqual(response.context['form'].material_type, category)
            self.assertFalse(response.context['form'].fields[GlazeForm.TYPE_FIELDS[category][0]].disabled)
        from django.template.loader import render_to_string
        icons = [render_to_string('partials/nav_icon.html', {'icon': category}) for category in Glaze.MaterialType.values]
        self.assertEqual(len(set(icons)), 3)

    def test_category_tabs_isolate_types_and_keep_workshop_permissions(self):
        workshop = Circle.objects.create(owner=self.other, name='Compartido')
        workshop.members.add(self.owner)
        materials = {}
        for category in Glaze.MaterialType.values:
            material = Glaze.objects.create(owner=self.other, group=workshop, name=category, material_type=category)
            materials[category] = material
            Glaze.objects.create(owner=self.other, name='Privado ' + category, material_type=category)
        for category, material in materials.items():
            response = self.client.get(reverse('glazes'), {'material_type': category})
            self.assertEqual(list(response.context['page'].object_list), [material])
            self.assertEqual(response.context['active_material_type'], category)
            tabs = response.content.decode().split('<nav class="library-tabs"', 1)[1].split('</nav>', 1)[0]
            self.assertEqual(tabs.count('<a '), 4)
            self.assertEqual(tabs.count('aria-current="page"'), 1)
            self.assertIn(f'?material_type={category}" class="active"', tabs)
            self.assertContains(response, f'name="material_type" value="{category}"')
            self.assertNotContains(response, '<select name="material_type">')
        for value in [None, '', 'invalid']:
            response = self.client.get(reverse('glazes'), {} if value is None else {'material_type': value})
            self.assertEqual(list(response.context['page'].object_list), [materials['glaze']])

    def test_empty_category_and_search_reset_keep_creation_in_selected_category(self):
        for category in Glaze.MaterialType.values:
            response = self.client.get(reverse('glazes'), {'material_type': category})
            self.assertContains(response, 'Todavía no hay materiales de este tipo.')
            self.assertNotContains(response, 'No hay coincidencias.')
            self.assertContains(response, reverse('glaze_new') + '?material_type=' + category)
            response = self.client.get(reverse('glazes'), {'material_type': category, 'q': 'sin resultados'}, HTTP_HX_REQUEST='true')
            self.assertContains(response, 'No hay coincidencias.')
            self.assertContains(response, reverse('glazes') + '?material_type=' + category)
            create = self.client.get(reverse('glaze_new'), {'material_type': category})
            self.assertContains(create, 'href="' + reverse('glazes') + '?material_type=' + category + '"')
