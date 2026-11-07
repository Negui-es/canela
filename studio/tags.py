import re
import unicodedata
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


def normalize_tag(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())


def parse_tags(value):
    names = list(dict.fromkeys(normalize_tag(part) for part in re.split(r'[,;\n]', value) if part.strip()))
    if len(names) > 20:
        raise ValidationError(_('Puedes añadir hasta 20 etiquetas por pieza.'))
    if any(len(name) > 40 for name in names):
        raise ValidationError(_('Cada etiqueta puede tener hasta 40 caracteres.'))
    return names
