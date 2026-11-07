from pathlib import Path
from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

@register.simple_tag
def asset(name):
    """Refresh local assets on change; keep hashed production URLs."""
    url = static(name)
    if settings.DEBUG:
        source = finders.find(name)
        if source:
            version = Path(source).stat().st_mtime_ns
            return f'{url}?v={version}'
    return url
