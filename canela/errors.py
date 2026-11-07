"""Public error responses never include exception details or request data."""
from django.http import HttpResponse
from django.template.loader import get_template
from django.utils.translation import gettext_lazy as _, get_language


MESSAGES = {
    400: (_('No hemos podido abrir esta página.'), _('La solicitud no se ha podido completar. Vuelve a intentarlo desde el inicio.')),
    403: (_('No podemos continuar por aquí.'), _('Puede que tu sesión haya caducado o que no tengas acceso. Vuelve al inicio para continuar.')),
    404: (_('Esta página no está aquí.'), _('Puede que el enlace haya cambiado o que esta página ya no esté disponible.')),
    500: (_('No todo sale a la primera.'), _('Esta vez, el problema está de nuestro lado. No hemos podido completar la acción. Vuelve a intentarlo en unos instantes.')),
}


def error_response(status):
    title, message = MESSAGES[status]
    # No request/context processors, database queries, static manifest or user data:
    # this page must still work when another part of the application fails.
    try:
        html = get_template('500.html' if status == 500 else 'error.html').render({'status': status, 'title': title, 'message': message, 'home_url':f'/{get_language()}/'})
    except Exception:
        html = f'<!doctype html><html lang="{get_language()}"><meta charset="utf-8"><title>Canela</title><h1>{title}</h1><p>{message}</p><a href="/{get_language()}/">{_("Volver al inicio")}</a></html>'
    response = HttpResponse(html, status=status)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['X-Frame-Options'] = 'DENY'
    response['Content-Language'] = get_language()
    return response


def bad_request(request, exception=None):
    return error_response(400)


def permission_denied(request, exception=None):
    return error_response(403)


def page_not_found(request, exception=None):
    return error_response(404)


def server_error(request):
    return error_response(500)


def csrf_failure(request, reason=''):
    return error_response(403)


class PublicErrorMiddleware:
    """Keep technical errors off public hosts even if DEBUG is enabled by mistake."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        response = self.get_response(request)
        host = request.META.get('HTTP_HOST', '').lower().split(':')[0]
        local = host in {'localhost', '127.0.0.1', 'testserver'}
        if response.status_code == 500 or (
            settings.DEBUG and not local and response.status_code in {400, 403, 404}
        ):
            safe_response = error_response(response.status_code)
            for header in ('Strict-Transport-Security', 'Referrer-Policy', 'Cross-Origin-Opener-Policy'):
                if header in response:
                    safe_response[header] = response[header]
            return safe_response
        return response
