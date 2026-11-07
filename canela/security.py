"""Keep public HTTPS mandatory while allowing direct access on this computer."""
from django.middleware.security import SecurityMiddleware


def is_direct_loopback_http(request):
    return (
        not request.is_secure()
        and request.META.get('REMOTE_ADDR') in {'127.0.0.1', '::1'}
        and request.get_host().split(':', 1)[0].lower() in {'localhost', '127.0.0.1'}
        and 'HTTP_X_FORWARDED_PROTO' not in request.META
        and 'HTTP_CF_CONNECTING_IP' not in request.META
        and 'HTTP_X_FORWARDED_FOR' not in request.META
    )


class OriginSecurityMiddleware(SecurityMiddleware):
    def process_request(self, request):
        if not is_direct_loopback_http(request):
            return super().process_request(request)

    def process_response(self, request, response):
        response = super().process_response(request, response)
        if is_direct_loopback_http(request):
            # Session and CSRF middleware have already set these cookies. Their
            # host-only scope keeps local cookies separate from the public site.
            from django.conf import settings
            for name in (settings.SESSION_COOKIE_NAME, settings.CSRF_COOKIE_NAME):
                if name in response.cookies:
                    response.cookies[name]['secure'] = False
        return response
