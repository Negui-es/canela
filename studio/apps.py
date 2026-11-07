from django.utils.translation import gettext_lazy as _
from django.apps import AppConfig

class StudioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'studio'
    verbose_name = _('Taller')
