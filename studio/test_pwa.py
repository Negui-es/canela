from io import BytesIO
from pathlib import Path
from PIL import Image
from django.conf import settings
from django.test import TestCase, override_settings
from .models import User


@override_settings(SECURE_SSL_REDIRECT=False)
class InstallableAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_user('pwa-review')

    def test_manifest_is_public_has_stable_identity_and_mobile_icons(self):
        for language in ['es','en','fr','de','it']:
            with self.assertNumQueries(0):
                response=self.client.get('/manifest.webmanifest',HTTP_ACCEPT_LANGUAGE=language)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response['Content-Type'],'application/manifest+json')
            self.assertFalse(response.cookies)
            manifest=response.json()
            self.assertEqual(manifest['id'],'/')
            self.assertEqual(manifest['start_url'],'/')
            self.assertEqual(manifest['scope'],'/')
            self.assertEqual(manifest['display'],'standalone')
            self.assertEqual(manifest['lang'],language)
            self.assertEqual(manifest['name'],'Canela')
            self.assertIn('192x192',[icon['sizes'] for icon in manifest['icons']])
            self.assertIn('512x512',[icon['sizes'] for icon in manifest['icons']])
            self.assertIn('maskable',[icon['purpose'] for icon in manifest['icons']])
        for name,size in [('app-192.png',192),('app-512.png',512),('app-maskable-512.png',512),('apple-touch-icon.png',180)]:
            with Image.open(settings.BASE_DIR/'static/images'/name) as image:
                self.assertEqual(image.size,(size,size))
                self.assertEqual(image.mode,'RGB')

    def test_worker_has_root_scope_correct_type_and_no_private_data(self):
        with self.assertNumQueries(0):
            response=self.client.get('/service-worker.js')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response['Service-Worker-Allowed'],'/')
        self.assertIn('text/javascript',response['Content-Type'])
        self.assertIn('no-store',response['Cache-Control'])
        self.assertContains(response,'canela-offline-')
        self.assertNotContains(response,'{{')
        self.assertFalse(response.cookies)

    def test_offline_pages_are_translated_self_contained_and_account_independent(self):
        self.client.force_login(self.owner)
        for language,heading in [('es','El taller necesita conexión.'),('en','The studio needs a connection.'),
                                  ('fr','L’atelier a besoin d’une connexion.'),('de','Das Atelier braucht eine Verbindung.'),
                                  ('it','Il laboratorio ha bisogno di una connessione.')]:
            with self.assertNumQueries(0):
                response=self.client.get(f'/offline/{language}/',HTTP_ACCEPT_LANGUAGE='ja')
            self.assertContains(response,heading)
            self.assertContains(response,f'lang="{language}"')
            self.assertEqual(response['Content-Language'],language)
            self.assertNotContains(response,'pwa-review')
            self.assertNotContains(response,'src="/static/')
            self.assertNotContains(response,'<form')
            self.assertFalse(response.cookies)
        self.assertEqual(self.client.get('/offline/ja/').status_code,404)

    def test_installation_is_available_on_login_and_account_in_every_language(self):
        from django.urls import reverse
        from django.utils.translation import override
        for language in ['es','en','fr','de','it']:
            with override(language):
                self.client.logout()
                response=self.client.get(reverse('login'))
                self.assertContains(response,'rel="manifest"')
                self.assertContains(response,'apple-mobile-web-app-capable')
                self.assertContains(response,'data-install-app')
                self.assertContains(response,'data-service-worker="/service-worker.js"')
                self.client.force_login(self.owner)
                self.assertContains(self.client.get(reverse('account')),'data-install-app')
