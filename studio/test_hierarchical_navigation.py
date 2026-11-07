from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from .models import Circle, User


@override_settings(LANGUAGE_CODE='es', SECURE_SSL_REDIRECT=False)
class HierarchicalNavigationTests(TestCase):
    def setUp(self):
        language = override('es')
        language.__enter__()
        self.addCleanup(language.__exit__, None, None, None)
        self.admin = User.objects.create_user('nav-admin')
        self.student = User.objects.create_user('nav-student')
        self.root = Circle.objects.create(owner=self.admin, name='Taller principal')
        self.child = Circle.objects.create(owner=self.admin, parent=self.root, name='Clase martes')
        self.sibling = Circle.objects.create(owner=self.admin, parent=self.root, name='Clase privada')
        self.child.members.add(self.student)
        self.client.force_login(self.student)

    def test_child_members_see_ancestors_and_nesting_without_sibling_access(self):
        response = self.client.get(reverse('dashboard'))
        tree = response.context['nav_workshop_tree']
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]['workshop'].pk, self.root.pk)
        self.assertEqual([node['workshop'].pk for node in tree[0]['children']], [self.child.pk])
        self.assertNotContains(response, 'workshop-tree-children')
        workshops = self.client.get(reverse('workshops'))
        self.assertContains(workshops, 'workshop-page-children')
        self.assertNotContains(workshops, self.sibling.name)
        self.assertNotContains(response, self.sibling.name)
        self.assertNotContains(response, 'Administrar taller')

    def test_mobile_has_five_destinations_with_no_second_menu(self):
        html = self.client.get(reverse('dashboard')).content.decode()
        bar = html.split('<nav class="mobile-nav ', 1)[1].split('</nav>', 1)[0]
        self.assertEqual(bar.count('<a '), 5)
        self.assertIn(reverse('inspiration'), bar)
        self.assertEqual(bar.count('<button '), 0)
        self.assertIn(reverse('galleries'), bar)
        self.assertNotIn('data-mobile-more', bar)
        self.assertIn(reverse('workshops'), bar)
        self.assertIn('Materiales', bar)
        self.assertNotIn('data-mobile-menu-trigger', html)
        self.assertNotIn('id="mobile-menu"', html)

    def test_library_tabs_share_one_primary_destination(self):
        for name in ['glazes', 'molds']:
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn('aria-label="Contenido de la biblioteca"', html)
            self.assertIn('Materiales', html)
            self.assertIn(f'href="{reverse("glazes")}"', html)
            self.assertIn(f'href="{reverse("molds")}"', html)
            bar = html.split('<nav class="mobile-nav ', 1)[1].split('</nav>', 1)[0]
            self.assertEqual(bar.count('aria-current="page"'), 1)
            self.assertIn('href="'+reverse('glazes')+'" class="active"', bar)

    def test_workshop_gallery_redirect_selects_galleries_and_does_not_expose_admin(self):
        response = self.client.get(reverse('workshop_galleries', args=[self.child.pk]), follow=True)
        self.assertNotContains(response, 'Gestionar taller')
        html = response.content.decode()
        bar = html.split('<nav class="mobile-nav ', 1)[1].split('</nav>', 1)[0]
        self.assertIn('href="'+reverse('galleries')+'" class="active"', bar)
        self.assertEqual(bar.count('aria-current="page"'), 1)

    def test_administration_is_inherited_only_by_admins(self):
        self.client.force_login(self.admin)
        tree = self.client.get(reverse('dashboard')).context['nav_workshop_tree']
        self.assertTrue(tree[0]['workshop'].can_manage)
        self.assertEqual(len(tree[0]['children']), 2)
        self.assertTrue(all(node['workshop'].can_manage for node in tree[0]['children']))
