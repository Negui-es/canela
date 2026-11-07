from django.contrib import admin
from django.urls import include, path
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import JavaScriptCatalog
from studio import views
from . import pwa

handler400 = 'canela.errors.bad_request'
handler403 = 'canela.errors.permission_denied'
handler404 = 'canela.errors.page_not_found'
handler500 = 'canela.errors.server_error'

urlpatterns = [path('manifest.webmanifest',pwa.manifest,name='pwa_manifest'),
               path('service-worker.js',pwa.service_worker,name='pwa_service_worker'),
               path('offline/<str:language>/',pwa.offline,name='pwa_offline'),
               path('admin/', admin.site.urls), path('health/',views.health,name='health'),
               path('fotos/<uuid:pk>/',views.photo,name='photo')]
urlpatterns += i18n_patterns(
    path('jsi18n/',JavaScriptCatalog.as_view(),name='javascript-catalog'),
    path('',include('studio.urls')),
)
