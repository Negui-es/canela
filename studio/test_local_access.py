from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, Client, override_settings
from django.urls import reverse
from canela.security import OriginSecurityMiddleware
from .models import User


@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver', 'canela.example.test'], SECURE_SSL_REDIRECT=True, SECURE_HSTS_SECONDS=31536000)
class OriginSecurityTests(SimpleTestCase):
    def test_only_direct_loopback_http_skips_https_redirect(self):
        middleware=OriginSecurityMiddleware(lambda request: HttpResponse('ok'))
        factory=RequestFactory()
        for host,remote,headers,local in [
            ('127.0.0.1:8000','127.0.0.1',{},True),
            ('localhost:8000','127.0.0.1',{},True),
            ('canela.example.test','127.0.0.1',{},False),
            ('127.0.0.1:8000','192.0.2.1',{},False),
            ('127.0.0.1:8000','127.0.0.1',{'HTTP_CF_CONNECTING_IP':'192.0.2.1'},False),
            ('127.0.0.1:8000','127.0.0.1',{'HTTP_X_FORWARDED_PROTO':'http'},False),
            ('localhost:8000','127.0.0.1',{'HTTP_X_FORWARDED_FOR':'192.0.2.1'},False),
        ]:
            with self.subTest(host=host,remote=remote,headers=headers):
                request=factory.get('/es/login/',HTTP_HOST=host,REMOTE_ADDR=remote,**headers)
                response=middleware(request)
                self.assertEqual(response.status_code,200 if local else 301)
                if local:self.assertNotIn('Strict-Transport-Security',response)


@override_settings(ALLOWED_HOSTS=['localhost', '127.0.0.1', 'testserver', 'canela.example.test'], CSRF_TRUSTED_ORIGINS=['https://canela.example.test'], DEBUG=False, SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True,
                   CSRF_COOKIE_SECURE=True, SECURE_HSTS_SECONDS=31536000)
class LocalLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_user('local-check',password='Local-test-password-934!')

    def test_local_http_login_with_csrf_and_session(self):
        client=Client(enforce_csrf_checks=True,HTTP_HOST='127.0.0.1:8000',REMOTE_ADDR='127.0.0.1')
        response=client.get('/es/iniciar-sesion/')
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.cookies[settings.CSRF_COOKIE_NAME]['secure'])
        response=client.post('/es/iniciar-sesion/',{'username':'local-check','password':'Local-test-password-934!',
            'csrfmiddlewaretoken':client.cookies[settings.CSRF_COOKIE_NAME].value},HTTP_ORIGIN='http://127.0.0.1:8000')
        self.assertEqual(response.status_code,302)
        self.assertFalse(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
        self.assertEqual(client.get('/es/').status_code,200)

    def test_public_https_retains_secure_cookies_and_hsts(self):
        client=Client(enforce_csrf_checks=True,HTTP_HOST='canela.example.test')
        response=client.get('/es/iniciar-sesion/',secure=True)
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.cookies[settings.CSRF_COOKIE_NAME]['secure'])
        self.assertIn('Strict-Transport-Security',response)
        response=client.post('/es/iniciar-sesion/',{'username':'local-check','password':'Local-test-password-934!',
            'csrfmiddlewaretoken':client.cookies[settings.CSRF_COOKIE_NAME].value},secure=True,HTTP_ORIGIN='https://canela.example.test')
        self.assertEqual(response.status_code,302)
        self.assertTrue(response.cookies[settings.SESSION_COOKIE_NAME]['secure'])
