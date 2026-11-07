"""One personal material library, including catalogs of accessible workshops."""
from .models import Glaze
from .permissions import accessible_circles, available_materials, visible


def materials_for(user, origin='', *, model=Glaze, include_unavailable=False):
    materials = visible(model.objects.all(), user)
    if not include_unavailable:
        materials = available_materials(materials)
    if origin == 'personal':
        return materials.filter(owner=user, group__isnull=True)
    circle = accessible_circles(user).filter(pk=origin).first() if origin else None
    if circle:
        from .permissions import circle_scope
        scope = circle_scope(circle)
        materials = materials.filter(group_id__in=scope)
    elif origin:
        return materials.none()
    return materials
