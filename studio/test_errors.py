"""Exercise real exception handling without adding failure routes to the app."""
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, SuspiciousOperation
from django.http import Http404, HttpResponse
from django.test import Client, SimpleTestCase, override_settings
from django.urls import path

from canela.errors import error_response


PRIVATE_DETAIL = r'PRIVATE-ERROR C:\Users\private\project\secret.py'


def broken(request):
    raise RuntimeError(PRIVATE_DETAIL)


def forbidden(request):
    raise PermissionDenied(PRIVATE_DETAIL)


def missing(request):
    raise Http404(PRIVATE_DETAIL)


def invalid(request):
    raise SuspiciousOperation(PRIVATE_DETAIL)


def post_target(request):
    return HttpResponse('ok')


handler400 = 'canela.errors.bad_request'
handler403 = 'canela.errors.permission_denied'
handler404 = 'canela.errors.page_not_found'
handler500 = 'canela.errors.server_error'
urlpatterns = [path('broken/', broken), path('forbidden/', forbidden),
               path('missing/', missing), path('invalid/', invalid), path('post/', post_target)]


@override_settings(ALLOWED_HOSTS=['testserver', 'canela.example.test'], ROOT_URLCONF=__name__, DEBUG=False, SECURE_SSL_REDIRECT=False, LANGUAGE_CODE='es')
class PublicErrorTests(SimpleTestCase):
    def assert_safe_error(self, response, status):
        self.assertContains(response, 'Volver al inicio', status_code=status)
        self.assertContains(response, f'CANELA · {status}', status_code=status)
        for detail in [PRIVATE_DETAIL, 'Traceback', 'RuntimeError', 'Python', 'Request Method', str(__file__)]:
            self.assertNotContains(response, detail, status_code=status)
        self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_exception_pages_hide_private_details(self):
        client = Client(raise_request_exception=False)
        for url, status in [('broken/',500), ('forbidden/',403), ('missing/',404), ('invalid/',400), ('unknown/',404)]:
            with self.subTest(url=url):
                self.assert_safe_error(client.get('/'+url, HTTP_HOST='canela.example.test'), status)

    def test_csrf_rejection_does_not_explain_internal_configuration(self):
        response = Client(enforce_csrf_checks=True).post('/post/', HTTP_HOST='canela.example.test')
        self.assert_safe_error(response,403)
        self.assertNotContains(response,'CSRF',status_code=403)

    @override_settings(DEBUG=True)
    def test_public_errors_stay_generic_if_debug_is_accidentally_enabled(self):
        client = Client(raise_request_exception=False)
        for url, status in [('broken/',500),('invalid/',400),('unknown/',404)]:
            with self.subTest(url=url):
                self.assert_safe_error(client.get('/'+url, HTTP_HOST='canela.example.test'), status)

    def test_error_page_does_not_require_static_assets_or_database(self):
        with patch('canela.errors.get_template',side_effect=RuntimeError(PRIVATE_DETAIL)):
            response = error_response(500)
        self.assertContains(response, 'Volver al inicio',status_code=500)
        self.assertNotContains(response,PRIVATE_DETAIL,status_code=500)
