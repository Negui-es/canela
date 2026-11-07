from django import template
from django.utils.translation import gettext as _
from studio.permissions import can_read

register = template.Library()


@register.simple_tag(takes_context=True)
def piece_clay(context, piece):
    if not piece.clay_material_id:
        return piece.clay
    user = context.get('user')
    if user and can_read(piece.clay_material, user):
        return piece.clay_material.name
    return _('Material privado')
