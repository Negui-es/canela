"""Public installation metadata and a generic, account-independent offline page."""
from functools import lru_cache
from hashlib import sha256
import json
from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.utils import translation
from django.utils.translation import gettext as _
from django.views.decorators.http import require_safe


@require_safe
def manifest(request):
    response = JsonResponse({
        'id':'/', 'name':'Canela', 'short_name':'Canela',
        'description':_('Tu cuaderno de taller, a tu ritmo.'),
        'lang':translation.get_language(), 'start_url':'/', 'scope':'/',
        'display':'standalone', 'background_color':'#f2e9db', 'theme_color':'#f2e9db',
        'prefer_related_applications':False,
        'icons':[
            {'src':static('images/app-192.png'),'sizes':'192x192','type':'image/png','purpose':'any'},
            {'src':static('images/app-512.png'),'sizes':'512x512','type':'image/png','purpose':'any'},
            {'src':static('images/app-maskable-512.png'),'sizes':'512x512','type':'image/png','purpose':'maskable'},
        ],
    }, content_type='application/manifest+json')
    response['Cache-Control']='no-cache'
    return response


@lru_cache(maxsize=1)
def worker_source():
    paths = list((settings.BASE_DIR/'templates/pwa').glob('*'))
    paths += list((settings.BASE_DIR/'locale').glob('*/LC_MESSAGES/django.mo'))
    digest = sha256(b''.join(path.read_bytes() for path in sorted(paths) if path.is_file())).hexdigest()[:16]
    languages = list(dict(settings.LANGUAGES))
    return render_to_string('pwa/service-worker.js',{
        'cache_name':f'canela-offline-{digest}',
        'languages':json.dumps(languages),
    })


@require_safe
def service_worker(request):
    response=HttpResponse(worker_source(),content_type='text/javascript; charset=utf-8')
    response['Cache-Control']='no-cache, no-store, must-revalidate'
    response['Service-Worker-Allowed']='/'
    return response


@require_safe
def offline(request, language):
    if language not in dict(settings.LANGUAGES):
        raise Http404
    with translation.override(language):
        html=render_to_string('pwa/offline.html',{'language':language})
    response=HttpResponse(html)
    response['Content-Language']=language
    response['X-Robots-Tag']='noindex, nofollow'
    response['Cache-Control']='no-store'
    return response
