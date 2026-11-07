"""Language negotiation, localized UI and unchanged privacy boundaries."""
from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from canela.errors import error_response
from .models import User, Piece, Mold, Glaze, Gallery, GalleryEntry, Circle, Progress, GlazeUse, Sample


@override_settings(LANGUAGE_CODE='en', SECURE_SSL_REDIRECT=False)
class LanguageRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_user('routing-example')
    def test_browser_preferences_and_english_fallback(self):
        for header, expected in [('', 'en'), ('ja,pt;q=0.8','en'), ('es-ES,es;q=0.9,en;q=0.7','es'),
                                 ('de-CH,de;q=0.9','de'), ('en;q=0.4,fr-CA;q=0.9','fr'), ('it-IT','it')]:
            with self.subTest(header=header):
                response=self.client.get('/?view=recent',HTTP_ACCEPT_LANGUAGE=header)
                self.assertEqual(response.status_code,307)
                self.assertEqual(response['Location'],f'/{expected}/?view=recent')
                self.assertIn('Accept-Language',response['Vary'])
                self.assertEqual(response['Cache-Control'],'private, no-store')

    def test_language_cookie_does_not_override_browser(self):
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME]='it'
        self.assertEqual(self.client.get('/',HTTP_ACCEPT_LANGUAGE='fr')['Location'],'/fr/')

    def test_explicit_prefix_wins(self):
        for code, text in [('es','Entrar'),('en','Sign in'),('fr','Entrer dans mon atelier'),('de','Mein Atelier öffnen'),('it','Accedi')]:
            with self.subTest(code=code):
                with translation.override(code):
                    url=reverse('login')
                response=self.client.get(url,HTTP_ACCEPT_LANGUAGE='es')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response['Content-Language'],code)
                self.assertContains(response,f'<html lang="{code}">')
                self.assertContains(response,text)
                self.assertNotContains(response,'set_language')

    def test_old_form_submission_uses_method_preserving_redirect(self):
        response=self.client.post('/login/?next=/piezas/',{'username':'example'},HTTP_ACCEPT_LANGUAGE='it')
        self.assertEqual(response.status_code,307)
        self.assertEqual(response['Location'],'/it/accedi/?next=/piezas/')

    def test_javascript_catalog_for_every_language(self):
        for language in ['es','en','fr','de','it']:
            response=self.client.get(f'/{language}/jsi18n/')
            self.assertEqual(response.status_code,200)
            self.assertContains(response,'gettext')
            self.assertContains(response,'ngettext')
            self.assertEqual(response['Content-Language'],language)

    def test_error_pages_are_localized_and_safe(self):
        for language in ['es','en','fr','de','it']:
            with translation.override(language):
                for status in [400,403,404,500]:
                    response=error_response(status)
                    self.assertEqual(response.status_code,status)
                    self.assertContains(response,f'lang="{language}"',status_code=status)
                    self.assertContains(response,f'href="/{language}/"',status_code=status)
                    self.assertNotContains(response,'Traceback',status_code=status)


@override_settings(LANGUAGE_CODE='en', SECURE_SSL_REDIRECT=False)
class TranslatedPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner=User.objects.create_user('language-owner',email='owner@example.test')
        cls.other=User.objects.create_user('language-other')
        cls.piece=Piece.objects.create(owner=cls.owner,name='Cuenco de prueba',notes='Mis notas en español')
        cls.mold=Mold.objects.create(owner=cls.owner,name='Molde del taller')
        cls.glaze=Glaze.objects.create(owner=cls.owner,name='Blanco avena')
        cls.sample=Sample.objects.create(glaze=cls.glaze,temperature=1230,clay='Gres')
        cls.gallery=Gallery.objects.create(owner=cls.owner,name='Mi colección',audience='public')
        GalleryEntry.objects.create(gallery=cls.gallery,piece=cls.piece,title='Cuenco público')
        cls.group=Circle.objects.create(owner=cls.owner,name='Nuestro taller')
        cls.group.members.add(cls.owner)
        cls.event=Progress.objects.create(piece=cls.piece,stage='raw')
        cls.use=GlazeUse.objects.create(piece=cls.piece,glaze=cls.glaze,layers=1)

    def test_all_primary_screens_render_in_every_language(self):
        self.client.force_login(self.owner)
        screens=[('dashboard',[]),('pieces',[]),('piece',[self.piece.pk]),('piece_new',[]),('piece_edit',[self.piece.pk]),
                 ('molds',[]),('mold_new',[]),('mold',[self.mold.pk]),('glazes',[]),('glaze_new',[]),('glaze',[self.glaze.pk]),
                 ('galleries',[]),('gallery_manage',[self.gallery.pk]),('gallery',[self.gallery.pk]),('gallery_new',[]),
                 ('circles',[]),('circle',[self.group.pk]),('account',[]),('progress_edit',[self.piece.pk,self.event.pk]),
                 ('glaze_use_edit',[self.piece.pk,self.use.pk]),('photos_manage',['sample',self.sample.pk])]
        for language in ['es','en','fr','de','it']:
            with translation.override(language):
                for name,args in screens:
                    with self.subTest(language=language,screen=name):
                        response=self.client.get(reverse(name,args=args))
                        self.assertEqual(response.status_code,200)
                        self.assertContains(response,f'<html lang="{language}">')
                        self.assertNotContains(response,'CNL')

    def test_content_stays_original_and_private(self):
        self.client.force_login(self.owner)
        response=self.client.get(f'/en/pieces/{self.piece.pk}/')
        self.assertContains(response,'Cuenco de prueba')
        self.assertContains(response,'Mis notas en español')
        self.assertNotContains(response,'Sin cantidades registradas')
        self.client.force_login(self.other)
        for language in ['es','en','fr','de','it']:
            with translation.override(language):
                url=reverse('piece',args=[self.piece.pk])
            response=self.client.get(url)
            self.assertEqual(response.status_code,404)
            self.assertNotContains(response,'Mis notas en español',status_code=404)

    def test_new_mold_suggestions_follow_language_without_modifying_existing_content(self):
        from .forms import MoldForm
        with translation.override('en'):
            form=MoldForm(user=self.owner)
            self.assertEqual(str(form.initial['material']),'Plaster')
            existing=MoldForm(user=self.owner,instance=self.mold)
            self.assertEqual(existing.initial['material'],'Escayola')

    def test_english_is_used_without_a_language_header(self):
        response=self.client.get('/login/')
        self.assertEqual(response['Location'],'/en/sign-in/')
