from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from django.utils.translation import pgettext_lazy
from . import views, photo_views, history_views, group_views, workshop_views, presentation_views

legacy_urlpatterns = [
    path('talleres/', workshop_views.workshop_list, name='workshops'),
    path('talleres/<uuid:workshop_id>/', workshop_views.workshop, name='workshop'),
    path('talleres/<uuid:workshop_id>/galerias/', workshop_views.workshop, {'tab': 'galleries'}, name='workshop_galleries'),
    path('talleres/<uuid:workshop_id>/materiales/', workshop_views.workshop, {'tab': 'materials'}, name='workshop_materials'),
    path('', views.dashboard, name='dashboard'),
    path('setup/', views.setup, name='setup'),
    path('login/', views.SignIn.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('cuenta/', views.account, name='account'),
    path('cuenta/password/', auth_views.PasswordChangeView.as_view(template_name='form.html', extra_context={'back': 'account'}, success_url=reverse_lazy('account')), name='password_change'),
    path('invitaciones/nueva/', views.invite, name='invite'),
    path('invitacion/<uuid:token>/', views.accept_invite, name='accept_invite'),
    path('inspiracion/', presentation_views.inspiration, name='inspiration'),
    path('piezas/<uuid:pk>/presentacion/', presentation_views.edit, name='presentation_edit'),
    path('piezas/<uuid:pk>/publicacion/', presentation_views.publication, name='presentation_publish'),
    path('piezas/', views.piece_list, name='pieces'),
    path('piezas/nueva/', views.piece_edit, name='piece_new'),
    path('piezas/<uuid:pk>/', views.piece_detail, name='piece'),
    path('piezas/<uuid:pk>/editar/', views.piece_edit, name='piece_edit'),
    path('piezas/<uuid:pk>/eliminar/', views.piece_delete, name='piece_delete'),
    path('piezas/<uuid:pk>/avance/', history_views.progress_edit, name='progress_add'),
    path('piezas/<uuid:pk>/avance/<int:event_id>/editar/', history_views.progress_edit, name='progress_edit'),
    path('piezas/<uuid:pk>/avance/<int:record_id>/eliminar/', history_views.remove, {'kind':'progress'}, name='progress_delete'),
    path('piezas/<uuid:pk>/esmalte/', views.glaze_use_add, name='glaze_use_add'),
    path('piezas/<uuid:pk>/esmalte/<int:use_id>/', views.glaze_use_add, name='glaze_use_edit'),
    path('piezas/<uuid:pk>/esmalte/<int:record_id>/eliminar/', history_views.remove, {'kind':'glaze'}, name='glaze_use_delete'),
    path('fotos/<uuid:pk>/eliminar/', photo_views.remove, name='photo_delete'),
    path('fotos/coleccion/<str:kind>/<uuid:pk>/', photo_views.manage, name='photos_manage'),
    path('moldes/', views.resource_list, {'kind':'mold'}, name='molds'),
    path('esmaltes/', views.resource_list, {'kind':'glaze'}, name='glazes'),
    path('moldes/nuevo/', views.resource_edit, {'kind':'mold'}, name='mold_new'),
    path('esmaltes/nuevo/', views.resource_edit, {'kind':'glaze'}, name='glaze_new'),
    path('moldes/<uuid:pk>/', views.resource_detail, {'kind':'mold'}, name='mold'),
    path('esmaltes/<uuid:pk>/', views.resource_detail, {'kind':'glaze'}, name='glaze'),
    path('moldes/<uuid:pk>/editar/', views.resource_edit, {'kind':'mold'}, name='mold_edit'),
    path('moldes/<uuid:pk>/eliminar/', views.material_delete, {'kind':'mold'}, name='mold_delete'),
    path('moldes/<uuid:pk>/disponibilidad/', views.material_retire, {'kind':'mold'}, name='mold_retire'),
    path('esmaltes/<uuid:pk>/editar/', views.resource_edit, {'kind':'glaze'}, name='glaze_edit'),
    path('esmaltes/<uuid:pk>/eliminar/', views.material_delete, name='material_delete'),
    path('esmaltes/<uuid:pk>/disponibilidad/', views.material_retire, name='material_retire'),
    path('esmaltes/<uuid:pk>/receta/', views.recipe_add, name='recipe_add'),
    path('esmaltes/<uuid:pk>/muestra/', views.sample_add, name='sample_add'),
    path('galerias/', views.gallery_list, name='galleries'),
    path('galerias/nueva/', views.gallery_edit, name='gallery_new'),
    path('galerias/<uuid:pk>/editar/', views.gallery_edit, name='gallery_edit'),
    path('galerias/<uuid:pk>/', views.gallery_manage, name='gallery_manage'),
    path('galerias/<uuid:pk>/añadir/', views.gallery_entry, name='gallery_entry'),
    path('galerias/<uuid:pk>/pieza/<uuid:entry_id>/editar/', views.gallery_entry, name='gallery_entry_edit'),
    path('galerias/<uuid:pk>/retirar/<uuid:entry_id>/', views.gallery_remove, name='gallery_remove'),
    path('g/<uuid:pk>/', views.gallery_public, name='gallery'),
    path('grupos/', group_views.circle_list, name='circles'),
    path('grupos/nuevo/', group_views.circle_new, name='circle_new'),
    path('grupos/<uuid:pk>/', group_views.circle_detail, name='circle'),
    path('grupos/<uuid:pk>/editar/', group_views.circle_edit, name='circle_edit'),
    path('grupos/<uuid:pk>/miembros/<int:user_id>/rol/', group_views.circle_role, name='circle_role'),
    path('grupos/<uuid:pk>/miembros/<int:user_id>/retirar/', group_views.circle_remove, name='circle_remove'),
]

# Keep the original routes for redirects; only these translated patterns are
# mounted in the application, so reverse() always produces the canonical URL.
urlpatterns = [
    path(pgettext_lazy('URL', str(pattern.pattern)) if str(pattern.pattern) else '',
         pattern.callback, pattern.default_args, name=pattern.name)
    for pattern in legacy_urlpatterns
]
