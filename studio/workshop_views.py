from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from .models import Glaze
from .permissions import accessible_circles, circle_scope, group_access, visible


@login_required
def workshop_list(request):
    return render(request, 'workshops.html', {'title': _('Talleres'), 'section': 'workshops'})


@login_required
def workshop(request, workshop_id, tab='home'):
    circle = get_object_or_404(accessible_circles(request.user).select_related('parent'), pk=workshop_id)
    if tab != 'materials':
        return redirect(reverse('galleries'))
    scope = circle_scope(circle)
    materials = visible(Glaze.objects.all(), request.user).filter(
        group_id__in=scope, availability='available').select_related('group').prefetch_related('photos', 'samples')
    if request.GET.get('q'):
        materials = materials.filter(name__icontains=request.GET['q'])
    if request.GET.get('material_type') in Glaze.MaterialType.values:
        materials = materials.filter(material_type=request.GET['material_type'])
    _, managed, direct = group_access(request.user)
    if tab == 'materials' and circle.pk not in managed:
        raise Http404
    return render(request, 'workshop.html', {
        'title': circle.name, 'section': 'workshop_' + tab, 'workshop': circle,
        'workshop_tab': tab,
        'workshop_materials': materials, 'can_manage_workshop': circle.pk in managed,
        'can_contribute_workshop': circle.pk in managed | direct,
        'material_types': Glaze.MaterialType.choices,
    })
