import re
import uuid
from django.conf import settings
from django.test import TestCase, Client, override_settings
from django.urls import resolve, reverse
from django.utils import translation
from .models import User, Piece
from .urls import legacy_urlpatterns


@override_settings(SECURE_SSL_REDIRECT=False, LANGUAGE_CODE='en')
class TranslatedRouteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_user('route-review')

    def test_primary_routes_use_the_language_of_the_prefix(self):
        names=['pieces','glazes','molds','galleries','circles','account','login']
        paths={
            'es':['piezas','esmaltes','moldes','galerias','grupos','cuenta','iniciar-sesion'],
            'en':['pieces','glazes','molds','galleries','groups','account','sign-in'],
            'fr':['pieces','emaux','moules','galeries','groupes','compte','connexion'],
            'de':['stuecke','glasuren','formen','galerien','gruppen','konto','anmelden'],
            'it':['pezzi','smalti','stampi','gallerie','gruppi','account','accedi'],
        }
        for language,segments in paths.items():
            with translation.override(language):
                for name,segment in zip(names,segments):
                    self.assertEqual(reverse(name),f'/{language}/{segment}/')

    def test_every_route_has_an_explicit_translation_in_each_catalog(self):
        import polib
        for language in dict(settings.LANGUAGES):
            catalog=polib.pofile(str(settings.BASE_DIR/'locale'/language/'LC_MESSAGES/django.po'))
            for pattern in legacy_urlpatterns:
                source=str(pattern.pattern)
                if source:
                    entry=catalog.find(source,msgctxt='URL')
                    self.assertIsNotNone(entry,(language,source))
                    self.assertTrue(entry.msgstr,(language,source))

    def test_every_translated_route_round_trips_and_legacy_links_redirect(self):
        identifier=uuid.UUID('11111111-2222-4333-8444-555555555555')
        for language in dict(settings.LANGUAGES):
            with translation.override(language):
                for pattern in legacy_urlpatterns:
                    kwargs={name:identifier if converter.__class__.__name__=='UUIDConverter' else 1 if converter.__class__.__name__=='IntConverter' else 'piece'
                            for name,converter in pattern.pattern.converters.items()}
                    canonical=reverse(pattern.name,kwargs=kwargs)
                    with self.subTest(language=language,route=pattern.name):
                        self.assertTrue(canonical.isascii())
                        match=resolve(canonical)
                        self.assertEqual(match.url_name,pattern.name)
                        self.assertEqual({k:match.kwargs[k] for k in kwargs},kwargs)
                        old=re.sub(r'<(?:[^:>]+:)?([^>]+)>',lambda m:str(kwargs[m[1]]),str(pattern.pattern))
                        source=f'/{language}/{old}'
                        if source != canonical:
                            response=self.client.get(source+'?q=a%2Bb&scope=shared',HTTP_ACCEPT_LANGUAGE='ja')
                            self.assertEqual(response.status_code,308)
                            self.assertEqual(response['Location'],canonical+'?q=a%2Bb&scope=shared')
                            self.assertEqual(response['Content-Language'],language)

    def test_unprefixed_legacy_and_translated_links_follow_browser_language(self):
        for source,header,target in [('/esmaltes/','en','/en/glazes/'),('/glazes/','en','/en/glazes/'),
                                     ('/moldes','it','/it/stampi/'),('/cuenta/','de','/de/konto/')]:
            response=self.client.get(source,HTTP_ACCEPT_LANGUAGE=header)
            self.assertEqual(response.status_code,307)
            self.assertEqual(response['Location'],target)
            self.assertIn('Accept-Language',response['Vary'])

    def test_legacy_post_preserves_data_and_only_creates_one_piece(self):
        self.client.force_login(self.owner)
        response=self.client.post('/en/piezas/nueva/',{'name':'Un nombre propio','started_on':'2026-10-25','stage':'raw'},follow=True)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.redirect_chain[0],('/en/pieces/new/',308))
        self.assertEqual(Piece.objects.filter(owner=self.owner,name='Un nombre propio').count(),1)

    def test_csrf_still_required_after_legacy_post_redirect(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response=client.post('/en/piezas/nueva/',{'name':'Should not exist'},follow=True)
        self.assertEqual(response.status_code,403)
        self.assertFalse(Piece.objects.filter(owner=self.owner).exists())

    def test_generated_links_and_auth_redirects_use_canonical_routes(self):
        response=self.client.get('/de/glasuren/')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response['Location'],'/de/anmelden/?next=/de/glasuren/')
        self.client.force_login(self.owner)
        response=self.client.get('/it/')
        self.assertContains(response,'href="/it/smalti/"')
        self.assertContains(response,'href="/it/pezzi/"')
        self.assertNotContains(response,'href="/it/esmaltes/"')

    def test_global_routes_keep_their_addresses_and_invalid_paths_stay_missing(self):
        for language in dict(settings.LANGUAGES):
            with translation.override(language):
                self.assertEqual(reverse('health'),'/health/')
                self.assertEqual(reverse('photo',args=[uuid.UUID(int=1)]),'/fotos/00000000-0000-0000-0000-000000000001/')
        self.assertEqual(self.client.get('/en/unknown/path/').status_code,404)
