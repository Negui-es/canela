from django.db.models import Q


def group_access(user):
    """Read ancestors of memberships; inherit administration downwards only."""
    if not user.is_authenticated:
        return set(), set(), set()
    from .models import Circle
    parents = dict(Circle.objects.values_list('pk', 'parent_id'))
    direct = set(Circle.objects.filter(members=user).values_list('pk', flat=True))
    managed = set(Circle.objects.filter(Q(owner=user) | Q(administrators=user)).values_list('pk', flat=True))
    while True:
        expanded = managed | {pk for pk, parent in parents.items() if parent in managed}
        if expanded == managed:
            break
        managed = expanded
    readable, frontier = direct | managed, direct | managed
    while frontier:
        frontier = {parents.get(pk) for pk in frontier} - readable - {None}
        readable |= frontier
    return readable, managed, direct


def accessible_circles(user):
    from .models import Circle
    return Circle.objects.filter(pk__in=group_access(user)[0])


def manageable_circles(user):
    from .models import Circle
    return Circle.objects.filter(pk__in=group_access(user)[1])


def sharing_circles(user):
    from .models import Circle
    _, managed, direct = group_access(user)
    return Circle.objects.filter(pk__in=managed | direct)


def circle_scope(circle):
    scope, current = set(), circle
    while current and current.pk not in scope:
        scope.add(current.pk)
        current = current.parent
    return scope


def visible(queryset, user):
    if not user.is_authenticated:
        return queryset.none()
    from .models import Glaze, Mold
    readable = group_access(user)[0]
    personal = Q(owner=user) | Q(shared_groups__in=readable)
    if queryset.model in (Glaze, Mold):
        return queryset.filter(Q(group__isnull=True, owner=user) | Q(group_id__in=readable)).distinct()
    return queryset.filter(personal).distinct()


def editable_materials(user, model=None):
    from .models import Glaze
    model = model or Glaze
    if not user.is_authenticated:
        return model.objects.none()
    return model.objects.filter(Q(group__isnull=True, owner=user) | Q(group_id__in=group_access(user)[1])).distinct()


def available_materials(queryset, *, unavailable=False):
    """Availability affects catalogs and new assignments, never historical access."""
    return queryset.exclude(availability='available') if unavailable else queryset.filter(availability='available')


def can_edit(resource, user):
    if not user.is_authenticated:
        return False
    if getattr(resource, 'group_id', None):
        return resource.group_id in group_access(user)[1]
    return resource.owner_id == user.pk


def can_read(resource, user):
    return user.is_authenticated and visible(type(resource).objects.filter(pk=resource.pk), user).exists()


def can_read_gallery(gallery, user):
    if gallery.workshop_id:
        return gallery.audience == 'public' or (user.is_authenticated and gallery.workshop_id in group_access(user)[0])
    return gallery.audience == 'public' or (user.is_authenticated and (
        gallery.owner_id == user.pk or (gallery.audience == 'group' and gallery.shared_groups.filter(pk__in=group_access(user)[0]).exists())
    ))


def can_manage_gallery(gallery, user):
    if not user.is_authenticated:
        return False
    if gallery.workshop_id:
        readable, managed, _ = group_access(user)
        return gallery.workshop_id in managed or (gallery.owner_id == user.pk and gallery.workshop_id in readable)
    return gallery.owner_id == user.pk


def can_contribute_gallery(gallery, user):
    if not user.is_authenticated:
        return False
    if gallery.workshop_id:
        _, managed, direct = group_access(user)
        return gallery.workshop_id in managed | direct
    return gallery.owner_id == user.pk
