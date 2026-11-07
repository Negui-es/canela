from copy import copy
from django.http import HttpResponseRedirect
from django.middleware.locale import LocaleMiddleware
from django.conf import settings
from django.urls import Resolver404, resolve, reverse
from django.urls.resolvers import RegexPattern, URLResolver
from django.utils.translation import get_language_from_path


class LanguageRedirect(HttpResponseRedirect):
    # Preserve submitted forms when following an old, unprefixed address.
    status_code = 307


class BrowserLocaleMiddleware(LocaleMiddleware):
    response_redirect_class = LanguageRedirect

    def process_request(self, request):
        # URL first, then browser preferences, then English. Ignore old language
        # cookies, without changing the original session/CSRF cookies.
        language_request = copy(request)
        language_request.COOKIES = {}
        super().process_request(language_request)
        request.LANGUAGE_CODE = language_request.LANGUAGE_CODE
        # Old bookmarks and forms used Spanish paths under every prefix. Resolve
        # them against frozen routes, then reverse in the selected language.
        try:
            resolve(request.path_info)
            return
        except Resolver404:
            pass
        from studio.urls import legacy_urlpatterns
        prefix = get_language_from_path(request.path_info)
        path = request.path_info[len(prefix)+1:] if prefix else request.path_info
        resolver = URLResolver(RegexPattern(r'^/'), legacy_urlpatterns)
        try:
            match = resolver.resolve(path)
        except Resolver404:
            if not settings.APPEND_SLASH or path.endswith('/'):
                return
            try:
                match = resolver.resolve(path + '/')
            except Resolver404:
                return
        target = reverse(match.url_name, kwargs=match.kwargs)
        query = request.META.get('QUERY_STRING', '')
        if query:
            target += '?' + query
        response = LanguageRedirect(target)
        response.status_code = 308 if prefix else 307
        response['Cache-Control'] = 'private, no-store'
        return response

    def process_response(self, request, response):
        response = super().process_response(request,response)
        if response.status_code in {307, 308}:
            response['Cache-Control'] = 'private, no-store'
        return response
