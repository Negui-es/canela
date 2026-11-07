def navigation(request):
    from django.conf import settings
    if not request.user.is_authenticated:
        return {'allow_new_accounts': settings.ALLOW_NEW_ACCOUNTS}
    from .models import Piece
    from .permissions import accessible_circles, group_access
    managed = group_access(request.user)[1]
    workshops = list(accessible_circles(request.user).select_related('parent').order_by('name'))
    for workshop in workshops:
        workshop.can_manage = workshop.pk in managed
    nodes = {workshop.pk: {'workshop': workshop, 'children': []} for workshop in workshops}
    roots = []
    for workshop in workshops:
        parent = nodes.get(workshop.parent_id)
        (parent['children'] if parent else roots).append(nodes[workshop.pk])
    def administration_tree(items):
        result = []
        for node in items:
            children = administration_tree(node['children'])
            if node['workshop'].can_manage or children:
                result.append({'workshop': node['workshop'], 'children': children})
        return result
    return {'piece_count': Piece.objects.filter(owner=request.user).count(),
            'nav_workshops': workshops,
            'nav_workshop_tree': roots,
            'nav_admin_workshop_tree': administration_tree(roots),
            'is_preview': getattr(settings, 'CANELA_PREVIEW', False),
            'allow_new_accounts': settings.ALLOW_NEW_ACCOUNTS}
