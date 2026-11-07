from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from .forms import AddMemberForm, CircleForm
from .models import Circle, Glaze, Invitation, Mold, Piece
from .permissions import accessible_circles, circle_scope, group_access, manageable_circles, visible


@login_required
def circle_list(request):
    circles = list(accessible_circles(request.user).select_related('parent').order_by('name'))
    nodes = {circle.pk: {'circle': circle, 'children': []} for circle in circles}
    roots = []
    for circle in circles:
        parent = nodes.get(circle.parent_id)
        (parent['children'] if parent else roots).append(nodes[circle.pk])
    return render(request, 'circles.html', {'title': _('Talleres'), 'section': 'circles', 'circles': circles, 'nodes': roots})


@login_required
def circle_new(request):
    try:
        parent = get_object_or_404(manageable_circles(request.user), pk=request.GET['parent']) if request.GET.get('parent') else None
    except (ValueError, ValidationError):
        raise Http404
    form = CircleForm(request.POST or None, user=request.user, initial={'parent': parent.pk} if parent else {})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            circle = form.save(commit=False)
            circle.owner = request.user
            circle.save()
            circle.members.add(request.user)
            circle.administrators.add(request.user)
        return redirect('circle', pk=circle.pk)
    return render(request, 'form.html', {'form': form, 'title': _('Nuevo subgrupo') if parent else _('Nuevo taller'), 'subtitle': parent.path if parent else _('Crear un grupo no comparte automáticamente ninguna pieza.'), 'section': 'circles', 'back': 'workshops', 'back_url': reverse('circle', args=[parent.pk]) if parent else reverse('workshops'), 'back_label': parent.name if parent else _('Talleres')})


@login_required
def circle_edit(request, pk):
    circle = get_object_or_404(manageable_circles(request.user), pk=pk)
    form = CircleForm(request.POST or None, instance=circle, user=request.user)
    if request.method == 'POST':
        with transaction.atomic():
            # Serialize tree changes so simultaneous moves cannot create cycles.
            list(Circle.objects.select_for_update().order_by('pk').values_list('pk', flat=True))
            circle = get_object_or_404(manageable_circles(request.user), pk=pk)
            form = CircleForm(request.POST, instance=circle, user=request.user)
            if form.is_valid():
                form.save()
                messages.success(request, _('Grupo actualizado.'))
                return redirect('circle', pk=pk)
    return render(request, 'form.html', {'form': form, 'title': _('Editar grupo'), 'section': 'circles', 'back_url': reverse('circle', args=[pk])})


@login_required
def circle_detail(request, pk):
    circle = get_object_or_404(accessible_circles(request.user).select_related('parent'), pk=pk)
    readable, managed, direct = group_access(request.user)
    can_manage = circle.pk in managed
    form = AddMemberForm(request.POST or None)
    if request.method == 'POST':
        if not can_manage:
            raise PermissionDenied
        if form.is_valid():
            circle.members.add(form.cleaned_data['username'])
            messages.success(request, _('Miembro añadido a este grupo. Puede consultar también lo publicado en sus grupos superiores.'))
            return redirect('circle', pk=pk)
    scope = circle_scope(circle)
    local_admin_ids = set(circle.administrators.values_list('pk', flat=True)) | {circle.owner_id}
    return render(request, 'circle.html', {
        'title': circle.name, 'circle': circle, 'section': 'circles', 'form': form,
        'can_manage': can_manage, 'show_members': can_manage or circle.pk in direct,
        'local_admin_ids': local_admin_ids,
        'children': circle.children.filter(pk__in=readable).order_by('name'),
        'ancestors': Circle.objects.filter(pk__in=scope - {circle.pk}).select_related('parent').order_by('name'),
        'pieces': visible(Piece.objects.all(), request.user).filter(shared_groups__in=scope).distinct(),
        'molds': visible(Mold.objects.all(), request.user).filter(group_id__in=scope).filter(availability='available'),
        'glazes': visible(Glaze.objects.all(), request.user).filter(group_id__in=scope, availability='available').select_related('group'),
        'invitations': Invitation.objects.filter(circle=circle, used_at__isnull=True, expires_at__gt=timezone.now()) if can_manage else [],
    })


def last_admin_response(request):
    return render(request, 'notice.html', {'title': _('El grupo necesita un administrador'), 'text': _('Nombra a otro administrador antes de retirar al último o cambiar su rol.')}, status=400)


@login_required
@require_POST
def circle_role(request, pk, user_id):
    with transaction.atomic():
        circle = get_object_or_404(Circle.objects.select_for_update(), pk=pk)
        if circle.pk not in group_access(request.user)[1]:
            raise PermissionDenied
        member = get_object_or_404(circle.members, pk=user_id)
        action = request.POST.get('role')
        if action == 'admin':
            circle.administrators.add(member)
        elif action == 'member':
            remaining = set(circle.administrators.values_list('pk', flat=True)) | {circle.owner_id}
            remaining.discard(member.pk)
            if not remaining:
                return last_admin_response(request)
            if circle.owner_id == member.pk:
                circle.owner_id = min(remaining)
                circle.save(update_fields=['owner'])
            circle.administrators.remove(member)
        else:
            return render(request, 'notice.html', {'title': _('Rol no válido')}, status=400)
    messages.success(request, _('Rol actualizado.'))
    return redirect('circle', pk=pk)


@login_required
@require_POST
def circle_remove(request, pk, user_id):
    with transaction.atomic():
        circle = get_object_or_404(Circle.objects.select_for_update(), pk=pk)
        if circle.pk not in group_access(request.user)[1]:
            raise PermissionDenied
        admins = set(circle.administrators.values_list('pk', flat=True)) | {circle.owner_id}
        if user_id in admins and not admins - {user_id}:
            return last_admin_response(request)
        if circle.owner_id == user_id:
            circle.owner_id = min(admins - {user_id})
            circle.save(update_fields=['owner'])
        circle.administrators.remove(user_id)
        circle.members.remove(user_id)
    if pk in group_access(request.user)[0]:
        return redirect('circle', pk=pk)
    return redirect('circles')
