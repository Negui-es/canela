from django.utils.translation import gettext_lazy as _
import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Case, Count, F, OuterRef, Q, Subquery, Value, When
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods
from .forms import (AccountForm, GalleryEntryForm, GalleryForm,
                    GlazeForm, GlazeUseForm, MoldForm, PieceForm, ProfileForm,
                    RecipeForm, SampleForm)
from .models import (Circle, Gallery, GalleryEntry, Glaze, Ingredient, Invitation,
                     LoginAttempt, Mold, Photo, Piece, Progress, RecipeVersion, Tag, User, MaterialAvailability)
from .tags import normalize_tag
from .permissions import (can_read, can_read_gallery, visible, can_edit, editable_materials, available_materials,
                          group_access, manageable_circles, sharing_circles,
                          can_manage_gallery, can_contribute_gallery, accessible_circles)
from .services import save_photos
from .library import materials_for

def health(request):
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:
        return HttpResponse('unavailable', status=503, content_type='text/plain')
    return HttpResponse('ok', content_type='text/plain')

def form_page(request, form, title, *, subtitle='', back='dashboard', **extra):
    template = extra.pop('template', 'form.html')
    return render(request, template, {'form':form, 'title':title, 'subtitle':subtitle, 'back':back, **extra})

def setup(request):
    if User.objects.exists():
        return redirect('login')
    if not settings.DEBUG or request.get_host().split(':')[0] not in {'localhost','127.0.0.1','[::1]'} or request.META.get('REMOTE_ADDR') not in {'127.0.0.1','::1'}:
        return HttpResponse(_('La primera cuenta se crea desde el propio servidor.'), status=403)
    form = AccountForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        lock_path = settings.BASE_DIR / '.setup.lock'
        try:
            lock = lock_path.open('x')
        except FileExistsError:
            return HttpResponse(_('Ya hay una configuración en curso. Vuelve a intentarlo.'), status=409)
        try:
            with transaction.atomic():
                if User.objects.exists():
                    return redirect('login')
                user = form.save(commit=False)
                user.is_staff = user.is_superuser = True
                user.save()
            login(request, user)
            messages.success(request, _('Tu taller está listo. Empieza con tu primera pieza.'))
            return redirect('dashboard')
        finally:
            lock.close()
            lock_path.unlink(missing_ok=True)
    return render(request, 'registration/setup.html', {'form':form})

class SignIn(LoginView):
    template_name = 'registration/login.html'
    redirect_authenticated_user = True

    def dispatch(self, request, *args, **kwargs):
        if not User.objects.exists():
            return redirect('setup')
        return super().dispatch(request, *args, **kwargs)

    def attempt_key(self):
        value = self.request.META.get('REMOTE_ADDR','') + ':' + self.request.POST.get('username','').strip().casefold()
        return hashlib.sha256(value.encode()).hexdigest()

    def post(self, request, *args, **kwargs):
        attempt = LoginAttempt.objects.filter(key=self.attempt_key()).first()
        if attempt and attempt.first_failure < timezone.now()-timedelta(minutes=15):
            attempt.delete()
            attempt = None
        if attempt and attempt.failures >= 8:
            form = self.get_form()
            form.add_error(None, _('Demasiados intentos. Espera 15 minutos antes de volver a entrar.'))
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        attempt, _unused = LoginAttempt.objects.get_or_create(key=self.attempt_key())
        LoginAttempt.objects.filter(pk=attempt.pk).update(failures=F('failures')+1)
        return super().form_invalid(form)

    def form_valid(self, form):
        LoginAttempt.objects.filter(key=self.attempt_key()).delete()
        return super().form_valid(form)

@login_required
def account(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, _('Perfil actualizado.'))
        return redirect('account')
    return render(request, 'account.html', {'form':form,'title':_('Mi cuenta'), 'section':'account', 'invitations':Invitation.objects.filter(created_by=request.user,used_at__isnull=True,expires_at__gt=timezone.now()).select_related('circle')})

@login_required
@require_POST
def invite(request):
    if not settings.ALLOW_NEW_ACCOUNTS:
        return render(request, 'notice.html', {'title':_('Las altas están cerradas'),'text':_('Por ahora no se pueden crear cuentas nuevas.')}, status=403)
    circle = None
    if request.POST.get('circle'):
        circle = get_object_or_404(manageable_circles(request.user), pk=request.POST['circle'])
    elif not request.user.is_staff:
        raise PermissionDenied
    invitation = Invitation.objects.create(created_by=request.user, circle=circle, expires_at=timezone.now()+timedelta(days=7))
    messages.success(request, _('Invitación creada. Copia el enlace y compártelo con la persona que quieras invitar. Caduca en 7 días y solo se puede usar una vez.'))
    return redirect('circle', pk=circle.pk) if circle else redirect('account')

def accept_invite(request, token):
    invitation = get_object_or_404(Invitation, pk=token)
    if not invitation.available:
        return render(request, 'notice.html', {'title':_('Esta invitación ya no está disponible'),'text':_('Puede haber caducado o haberse utilizado. Pide una nueva invitación.')}, status=410)
    if request.user.is_authenticated:
        if request.method == 'POST':
            with transaction.atomic():
                invitation = Invitation.objects.select_for_update().get(pk=token)
                if not invitation.available:
                    return HttpResponse(_('Invitación ya utilizada.'), status=410)
                if invitation.circle:
                    invitation.circle.members.add(request.user)
                invitation.used_by = request.user
                invitation.used_at = timezone.now()
                invitation.save()
            return redirect('circle',pk=invitation.circle_id) if invitation.circle else redirect('dashboard')
        return render(request, 'registration/invite.html', {'invitation':invitation})
    if not settings.ALLOW_NEW_ACCOUNTS:
        return render(request, 'notice.html', {'title':_('Las altas están cerradas'),'text':_('Por ahora no se pueden crear cuentas nuevas. Si ya tienes una cuenta, inicia sesión.')}, status=403)
    form = AccountForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().get(pk=token)
            if not invitation.available:
                return HttpResponse(_('Invitación ya utilizada.'), status=410)
            user = form.save()
            if invitation.circle:
                invitation.circle.members.add(user)
            invitation.used_by = user
            invitation.used_at = timezone.now()
            invitation.save()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'registration/invite.html', {'form':form, 'invitation':invitation})

def filtered_pieces(request):
    qs = visible(Piece.objects.all(), request.user) if request.GET.get('scope') == 'shared' else Piece.objects.filter(owner=request.user)
    if request.GET.get('stage') == 'open':
        qs = qs.exclude(stage='finished')
    elif request.GET.get('stage') in Piece.Stage.values:
        qs = qs.filter(stage=request.GET['stage'])
    query = request.GET.get('q', '').strip()
    if query:
        readable_clays = visible(Glaze.objects.all(), request.user)
        qs = qs.filter(Q(name__icontains=query) | Q(clay_material__isnull=True, clay__icontains=query) |
            Q(clay_material__in=readable_clays, clay_material__name__icontains=query) |
            Q(technique__icontains=query) | Q(tags__name__icontains=normalize_tag(query)))
    if request.GET.get('tag'):
        qs = qs.filter(tags__name=normalize_tag(request.GET['tag']))
    return qs.distinct().select_related('owner', 'clay_material', 'presentation').prefetch_related('photos','shared_groups','tags')

@login_required
def dashboard(request):
    pieces = Piece.objects.filter(owner=request.user)
    return render(request, 'dashboard.html', {
        'section':'dashboard','title':_('Mi espacio'),
        'pieces':pieces.select_related('presentation').prefetch_related('photos','shared_groups','tags')[:6],
        'total':pieces.count(),'open_count':pieces.exclude(stage='finished').count(),
        'glaze_count':materials_for(request.user).count(),
        'mold_count':materials_for(request.user, model=Mold).count(),
    })

@login_required
def piece_list(request):
    page = Paginator(filtered_pieces(request), 18).get_page(request.GET.get('page'))
    tag_scope = visible(Piece.objects.all(), request.user) if request.GET.get('scope') == 'shared' else Piece.objects.filter(owner=request.user)
    tags = Tag.objects.filter(pieces__in=tag_scope).distinct()
    selected_tag = normalize_tag(request.GET.get('tag', ''))
    ctx = {'section':'pieces','title':_('Mis piezas'), 'pieces':page,'page':page,'stages':[('open',_('Procesos abiertos')),*Piece.Stage.choices], 'tags': tags, 'selected_tag': selected_tag, 'unknown_tag': bool(selected_tag) and not tags.filter(name=selected_tag).exists(), 'refresh_tag_filter': bool(request.headers.get('HX-Request'))}
    return render(request, 'partials/piece_results.html' if request.headers.get('HX-Request') else 'pieces.html', ctx)

@login_required
def piece_delete(request, pk):
    piece = get_object_or_404(Piece, pk=pk, owner=request.user)
    if request.method not in {'GET', 'POST'}:
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET', 'POST'])
    confirmed = request.method == 'POST' and request.POST.get('confirm_delete') == 'yes'
    if confirmed:
        from .services import delete_piece
        with transaction.atomic():
            piece = get_object_or_404(Piece.objects.select_for_update(), pk=pk, owner=request.user)
            delete_piece(piece)
        messages.success(request, _('Pieza eliminada.'))
        return redirect('pieces')
    return render(request, 'piece_delete.html', {
        'title':_('Eliminar pieza'), 'section':'pieces', 'piece':piece,
        'gallery_count':piece.gallery_entries.count(),
        'confirmation_error':request.method == 'POST',
    }, status=400 if request.method == 'POST' else 200)


@login_required
def piece_edit(request, pk=None):
    piece = get_object_or_404(Piece, pk=pk, owner=request.user) if pk else None
    previous_stage = piece.stage if piece else None
    form = PieceForm(request.POST or None, request.FILES or None, user=request.user, instance=piece)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            form.save_m2m()
            if request.POST.get('tags_present') == '1' or 'tag_names' in request.POST:
                form.save_tags(obj)
            if request.POST.get('glazes_present') == '1' or 'glazes' in request.POST:
                form.save_glazes(obj)
            event = None
            if not piece or previous_stage != obj.stage:
                event = Progress.objects.create(piece=obj, stage=obj.stage, date=obj.started_on if not piece else timezone.localdate())
            save_photos(form.cleaned_data['photos'], piece=obj, progress=event)
            if request.POST.get('galleries_present') == '1' or 'galleries' in request.POST:
                form.save_galleries(obj)
        messages.success(request, _('Pieza guardada.'))
        return redirect('piece', pk=obj.pk)
    return form_page(request, form, _('Editar pieza') if piece else _('Nueva pieza'), back='pieces', section='pieces', template='piece_form.html', editing=piece is not None)

@login_required
def piece_detail(request, pk):
    piece = get_object_or_404(visible(Piece.objects.all(), request.user).select_related('mold','owner','clay_material').prefetch_related('tags'), pk=pk)
    # Access to a linked resource is checked independently of access to the piece.
    mold_visible = piece.mold and can_read(piece.mold, request.user)
    clay_visible = piece.clay_material_id and can_read(piece.clay_material, request.user)
    uses = []
    for use in piece.glaze_uses.select_related('glaze','recipe_version'):
        use.glaze_visible = can_read(use.glaze, request.user)
        use.glaze_editable = can_edit(use.glaze, request.user)
        if use.glaze_visible or piece.owner_id==request.user.pk:
            uses.append(use)
    return render(request, 'piece.html', {'section':'pieces','title':piece.name,'piece':piece,'can_edit':piece.owner_id==request.user.pk,'mold_visible':mold_visible,'clay_visible':clay_visible,'uses':uses,'events':piece.progress.prefetch_related('photos')})

@login_required
def glaze_use_add(request, pk, use_id=None):
    piece = get_object_or_404(Piece, pk=pk, owner=request.user)
    instance = get_object_or_404(piece.glaze_uses.all(), pk=use_id) if use_id else None
    previous_glaze = instance.glaze_id if instance else None
    form = GlazeUseForm(request.POST or None, user=request.user, instance=instance)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            piece = get_object_or_404(Piece.objects.select_for_update(),pk=pk,owner=request.user)
            use = form.save(commit=False)
            use.piece = piece
            if not instance or previous_glaze != use.glaze_id:
                use.recipe_version = use.glaze.latest_recipe
            use.save()
            piece.save(update_fields=['updated_at'])
        messages.success(request, _('Uso de material guardado.'))
        return redirect('piece',pk=pk)
    return form_page(request, form, _('Detalles de uso') if instance else _('Añadir material'), subtitle=piece.name, section='pieces', back_url=reverse('piece',args=[pk]))

def photo(request, pk):
    obj = get_object_or_404(Photo.objects.select_related('piece','mold','glaze','sample__glaze'),pk=pk)
    parent = obj.piece or obj.mold or obj.glaze or obj.sample.glaze
    allowed = can_read(parent, request.user)
    if not allowed and obj.piece_id:
        from .models import PiecePresentation
        presentation = PiecePresentation.objects.filter(piece_id=obj.piece_id, photos=obj).first()
        if presentation:
            allowed = (presentation.published or any(
                can_read_gallery(entry.gallery, request.user)
                for entry in obj.piece.gallery_entries.select_related('gallery')
            ))
        elif not PiecePresentation.objects.filter(piece_id=obj.piece_id).exists():
            # Compatibility for legacy imports without a canonical presentation.
            allowed = any(can_read_gallery(entry.gallery, request.user)
                          for entry in obj.gallery_entries.select_related('gallery'))
    if not allowed:
        raise Http404
    file = obj.thumbnail if request.GET.get('thumb') else obj.image
    try:
        response = FileResponse(file.open('rb'), content_type='image/jpeg')
    except FileNotFoundError:
        raise Http404
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response

RESOURCE_TYPES = {'mold':(Mold,MoldForm,'molds',_('Moldes')), 'glaze':(Glaze,GlazeForm,'glazes',_('Materiales'))}

@login_required
def resource_list(request, kind):
    model, _unused, section, label = RESOURCE_TYPES[kind]
    show_unavailable = request.GET.get('unavailable') == '1' or request.GET.get('retired') == '1'
    library_origins = accessible_circles(request.user).order_by('name')
    try:
        resources = materials_for(request.user, request.GET.get('origin', ''), model=model, include_unavailable=show_unavailable)
    except (ValueError, ValidationError):
        resources = model.objects.none()
    if show_unavailable:
        resources = available_materials(resources.filter(pk__in=editable_materials(request.user, model).values('pk')), unavailable=True)
    if request.GET.get('q'):
        resources = resources.filter(name__icontains=request.GET['q'])
    if kind == 'mold' and request.GET.get('state') in dict(Mold._meta.get_field('state').choices):
        resources = resources.filter(state=request.GET['state'])
    active_material_type = ''
    create_label = _('Nuevo molde')
    reset_url = reverse(section)
    create_url = reverse('mold_new') if kind == 'mold' else reverse('glaze_new')
    if kind == 'glaze':
        active_material_type = request.GET.get('material_type', 'glaze')
        if active_material_type not in Glaze.MaterialType.values:
            active_material_type = 'glaze'
        resources = resources.filter(material_type=active_material_type)
        create_label = {'clay': _('Nuevo barro'), 'glaze': _('Nuevo esmalte'), 'engobe': _('Nuevo engobe')}[active_material_type]
        reset_url += '?material_type=' + active_material_type
        create_url += '?material_type=' + active_material_type
    active_url = reset_url
    if show_unavailable:
        reset_url += ('&' if '?' in reset_url else '?') + 'unavailable=1'
    resources = resources.select_related('group').prefetch_related('photos') if kind == 'mold' else resources.select_related('group').prefetch_related('samples','photos')
    page = Paginator(resources,18).get_page(request.GET.get('page'))
    if kind in ('glaze', 'mold'):
        readable = group_access(request.user)[0]
        for material in page:
            origins = []
            if material.group_id in readable:
                origins.append(material.group.name)
            elif material.group_id is None and material.owner_id == request.user.pk:
                origins.append(str(_('Personal')))
            material.library_origins = origins
    return render(request,'partials/resource_results.html' if request.headers.get('HX-Request') else 'library.html',{'title':label,'section':section,'label':label,'kind':kind,'resources':page,'page':page,'states':[choice for choice in Mold._meta.get_field('state').choices if choice[0] != 'retired'],'material_types':Glaze.MaterialType.choices,'library_origins':library_origins,'active_material_type':active_material_type,'reset_url':reset_url,'create_url':create_url,'create_label':create_label,'show_unavailable':show_unavailable,'active_url':active_url,'unavailable_url':active_url + ('&' if '?' in active_url else '?') + 'unavailable=1','can_manage_catalog':editable_materials(request.user,model).exists() or manageable_circles(request.user).exists()})

@login_required
def resource_edit(request, kind, pk=None):
    model, form_type, section, label = RESOURCE_TYPES[kind]
    instance = get_object_or_404(editable_materials(request.user, model), pk=pk) if pk else None
    initial = {'material_type': request.GET['material_type']} if kind == 'glaze' and request.GET.get('material_type') in Glaze.MaterialType.values else {}
    if request.GET.get('group'):
        try:
            group_id = uuid.UUID(request.GET['group'])
        except ValueError:
            raise Http404
        initial['group'] = get_object_or_404(manageable_circles(request.user), pk=group_id).pk
    form = form_type(request.POST or None,request.FILES or None,instance=instance,user=request.user,initial=initial)
    if request.method=='POST' and 'preview_material' not in request.POST and form.is_valid():
        with transaction.atomic():
            obj = form.save(commit=False)
            if not instance:
                obj.owner = request.user
            obj.save()
            form.save_m2m()
            if kind=='mold':
                save_photos(form.cleaned_data['photos'],mold=obj)
            else:
                save_photos(form.cleaned_data['photos'],glaze=obj)
        messages.success(request,_('Guardado en tu cuaderno.'))
        return redirect(kind,pk=obj.pk)
    workshop = None
    if kind == 'glaze':
        group_id = instance.group_id if instance else initial.get('group')
        if group_id:
            workshop = accessible_circles(request.user).filter(pk=group_id).first()
    back_url = reverse(kind, args=[instance.pk]) if instance else reverse(section)
    material_title = _('Nuevo material')
    if kind == 'glaze':
        material_type = form.material_type if form.material_type in Glaze.MaterialType.values else 'glaze'
        if not instance:
            back_url += '?material_type=' + material_type
        material_title = {'clay': _('Nuevo barro'), 'glaze': _('Nuevo esmalte'), 'engobe': _('Nuevo engobe')}[material_type]
    return form_page(request,form,((_('Editar molde') if instance else _('Nuevo molde')) if kind=='mold' else (_('Editar material') if instance else material_title)),section=section,back=section,back_url=back_url,template='resource_form.html',kind=kind,editing=instance is not None,workshop=None)

@login_required
def resource_detail(request, kind, pk):
    model, _unused, section, _unused = RESOURCE_TYPES[kind]
    obj = get_object_or_404(visible(model.objects.all(),request.user),pk=pk)
    workshop = None
    if kind == 'glaze':
        if request.GET.get('workshop'):
            try:
                workshop_id = uuid.UUID(request.GET['workshop'])
            except ValueError:
                raise Http404
            workshop = get_object_or_404(accessible_circles(request.user), pk=workshop_id)
        elif obj.group_id:
            workshop = accessible_circles(request.user).filter(pk=obj.group_id).first()
    related_pieces = visible(Piece.objects.all(),request.user).filter(mold=obj) if kind=='mold' else visible(Piece.objects.all(),request.user).filter(Q(glaze_uses__glaze=obj) | Q(clay_material=obj)).distinct()
    return render(request,'resource.html',{'title':obj.name,'section':section,'kind':kind,'obj':obj,'can_edit':can_edit(obj, request.user),'pieces':related_pieces.select_related('presentation'),'versions':obj.versions.prefetch_related('ingredients').order_by('-number') if kind=='glaze' else [],'workshop':None,'availability_choices':MaterialAvailability.choices})


@login_required
@require_http_methods(['GET', 'POST'])
def material_delete(request, pk, kind='glaze'):
    from django.db.models.deletion import ProtectedError
    from .services import delete_material, material_has_history
    model = Mold if kind == 'mold' else Glaze
    material = get_object_or_404(editable_materials(request.user, model), pk=pk)
    blocked = material_has_history(material)
    confirmed = request.method == 'POST' and request.POST.get('confirm_delete') == 'yes'
    if confirmed and not blocked:
        try:
            with transaction.atomic():
                material = get_object_or_404(editable_materials(request.user, model).select_for_update(), pk=pk)
                material_type = material.material_type if kind == 'glaze' else ''
                delete_material(material)
        except ProtectedError:
            blocked = True
        else:
            messages.success(request, _('Molde eliminado.') if kind == 'mold' else _('Material eliminado.'))
            return redirect(reverse('molds') if kind == 'mold' else reverse('glazes') + '?material_type=' + material_type)
    return render(request, 'material_delete.html', {
        'title': _('Eliminar molde') if kind == 'mold' else _('Eliminar material'), 'section': 'molds' if kind == 'mold' else 'glazes', 'kind': kind, 'material': material,
        'blocked': blocked, 'confirmation_error': request.method == 'POST' and not confirmed,
    }, status=409 if request.method == 'POST' and blocked else 400 if request.method == 'POST' else 200)


@login_required
@require_POST
def material_retire(request, pk, kind='glaze'):
    model = Mold if kind == 'mold' else Glaze
    availability = request.POST.get('availability')
    if availability is None:
        availability = {'retire': 'retired', 'restore': 'available'}.get(request.POST.get('action'))
    if availability not in MaterialAvailability.values:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest(_('Acción no válida.'))
    with transaction.atomic():
        material = get_object_or_404(editable_materials(request.user, model).select_for_update(), pk=pk)
        material.availability = availability
        material.save(update_fields=['availability', 'updated_at'])
    messages.success(request, _('Disponibilidad actualizada.'))
    return redirect(kind, pk=pk)

@login_required
def recipe_add(request, pk):
    glaze = get_object_or_404(editable_materials(request.user),pk=pk,kind='recipe')
    latest = glaze.latest_recipe
    initial = {'ingredients':'\n'.join(f'{i.name}; {i.percentage}' for i in latest.ingredients.all())} if latest else {}
    form = RecipeForm(request.POST or None,initial=initial)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            locked = Glaze.objects.select_for_update().get(pk=pk)
            latest = locked.latest_recipe
            version = RecipeVersion.objects.create(glaze=locked,number=latest.number+1 if latest else 1,notes=form.cleaned_data['notes'])
            Ingredient.objects.bulk_create([Ingredient(version=version,name=name,percentage=value) for name,value in form.cleaned_data['ingredients']])
        messages.success(request,_('Nueva versión guardada. Las piezas y muestras anteriores conservan la receta que usaron.'))
        return redirect('glaze',pk=pk)
    return form_page(request,form,_('Una nueva versión de la receta'),subtitle=glaze.name,section='glazes',back_url=reverse('glaze',args=[pk]))

@login_required
def sample_add(request, pk):
    glaze = get_object_or_404(editable_materials(request.user),pk=pk)
    form = SampleForm(request.POST or None,request.FILES or None,material=glaze)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            sample = form.save(commit=False)
            sample.glaze = glaze
            sample.recipe_version = glaze.latest_recipe
            sample.save()
            save_photos(form.cleaned_data['photos'],sample=sample)
        return redirect('glaze',pk=pk)
    return form_page(request,form,_('Guardar una prueba'),subtitle=glaze.name,section='glazes',back_url=reverse('glaze',args=[pk]))

@login_required
def gallery_list(request):
    readable = group_access(request.user)[0]
    # A gallery cover must come from its explicitly selected photos, never
    # from other pictures in a contributor's private piece history.
    cover_photos = Photo.objects.filter(
        Q(presentations__piece__gallery_entries__gallery_id=OuterRef('pk')) |
        Q(gallery_entries__gallery_id=OuterRef('pk'), gallery_entries__piece__presentation__isnull=True)
    ).annotate(cover_rank=Case(When(presentations__cover_id=F('pk'), then=Value(0)), default=Value(1))).order_by('cover_rank', 'position', '-created_at', 'pk')
    galleries = list(Gallery.objects.filter(
        Q(workshop_id__in=readable) |
        Q(workshop__isnull=True, owner=request.user) |
        Q(workshop__isnull=True, audience='group', shared_groups__in=readable)
    ).distinct().select_related('owner', 'workshop__parent').annotate(
        entry_total=Count('entries', distinct=True),
        cover_photo_id=Subquery(cover_photos.values('pk')[:1]),
    ).order_by('name'))
    return render(request, 'galleries.html', {
        'title': _('Galerías'), 'section': 'galleries', 'galleries': galleries, 'gallery_catalog': True,
    })


@login_required
def gallery_manage(request, pk):
    gallery = get_object_or_404(Gallery.objects.select_related('workshop'), pk=pk)
    if not can_read_gallery(gallery, request.user) or (not gallery.workshop_id and gallery.owner_id != request.user.pk):
        raise Http404
    can_manage = can_manage_gallery(gallery, request.user)
    can_contribute = can_contribute_gallery(gallery, request.user)
    entries = list(gallery.entries.select_related('piece__owner', 'piece__clay_material', 'piece__presentation').prefetch_related('piece__presentation__photos', 'photos', 'piece__glaze_uses__glaze'))
    for entry in entries:
        entry.can_edit_entry = entry.piece.owner_id == request.user.pk and can_contribute
        entry.can_remove_entry = entry.can_edit_entry or can_manage
        entry.visible_materials = []
        if gallery.workshop_id:
            materials = [use.glaze for use in entry.piece.glaze_uses.all()]
            if entry.piece.clay_material_id and entry.piece.clay_material_id not in {material.pk for material in materials}:
                materials.insert(0, entry.piece.clay_material)
            for material in materials:
                allowed = can_read(material, request.user)
                entry.visible_materials.append({
                    'name': material.name if allowed else '',
                    'url': reverse('glaze', args=[material.pk]) + f'?workshop={gallery.workshop_id}' if allowed else '',
                })
    return render(request,'gallery_manage.html',{
        'title':gallery.name,'section':'galleries','gallery':gallery,
        'entries':entries, 'workshop': gallery.workshop,
        'can_manage_gallery': can_manage, 'can_contribute_gallery': can_contribute,
        'gallery_link':request.build_absolute_uri(reverse('gallery',args=[pk])),
    })

@login_required
def gallery_edit(request, pk=None):
    obj = get_object_or_404(Gallery.objects.select_related('workshop'),pk=pk) if pk else None
    if obj and not can_manage_gallery(obj, request.user):
        raise Http404
    initial, workshop = {}, obj.workshop if obj else None
    if not obj and request.GET.get('workshop'):
        try:
            workshop_id = uuid.UUID(request.GET['workshop'])
        except ValueError:
            raise Http404
        workshop = get_object_or_404(sharing_circles(request.user), pk=workshop_id)
        initial = {'workshop': workshop.pk, 'audience': 'group'}
    form = GalleryForm(request.POST or None,instance=obj,user=request.user,initial=initial)
    if request.method=='POST' and form.is_valid():
        obj = form.save(commit=False)
        if obj._state.adding:
            obj.owner = request.user
        obj.save()
        form.save_m2m()
        messages.success(request,_('Galería guardada.'))
        return redirect('gallery_manage',pk=obj.pk)
    return form_page(request,form,_('Ajustes de la galería') if obj else _('Nueva galería'),section='galleries',back='galleries',template='gallery_form.html',gallery=obj,workshop=workshop)

@login_required
def gallery_entry(request, pk, entry_id=None):
    gallery = get_object_or_404(Gallery.objects.select_related('workshop'),pk=pk)
    if not can_contribute_gallery(gallery, request.user):
        raise Http404
    instance = get_object_or_404(GalleryEntry,pk=entry_id,gallery=gallery,piece__owner=request.user) if entry_id else None
    piece = None
    candidate = request.POST.get('piece') if request.method=='POST' else request.GET.get('piece')
    if instance:
        piece = instance.piece
        if candidate and candidate != str(piece.pk):
            raise Http404
    elif candidate:
        try:
            piece_id = uuid.UUID(candidate)
        except ValueError:
            raise Http404
        piece = get_object_or_404(Piece,pk=piece_id,owner=request.user)
    if not piece:
        if request.method=='POST':
            return HttpResponse(_('Selecciona primero una pieza.'),status=400)
        pieces = Piece.objects.filter(owner=request.user).exclude(gallery_entries__gallery=gallery).prefetch_related('photos')
        return render(request,'gallery_choose_piece.html',{'title':_('Añadir una pieza'),'section':'galleries','gallery':gallery,'pieces':pieces,'workshop':gallery.workshop})
    from .presentation_views import edit
    return edit(request, pk=piece.pk, gallery_id=gallery.pk)


def gallery_public(request, pk):
    gallery = get_object_or_404(Gallery.objects.select_related('owner'),pk=pk)
    if not can_read_gallery(gallery,request.user):
        raise Http404
    return render(request,'gallery.html',{'title':gallery.name,'gallery':gallery,'entries':gallery.entries.select_related('piece__presentation', 'piece__owner').prefetch_related('photos', 'piece__presentation__photos'),'is_owner':can_manage_gallery(gallery, request.user),'section':'galleries'})

@login_required
@require_POST
def gallery_remove(request, pk, entry_id):
    entry = get_object_or_404(GalleryEntry.objects.select_related('gallery', 'piece'),pk=entry_id,gallery_id=pk)
    if not (can_manage_gallery(entry.gallery, request.user) or
            (entry.piece.owner_id == request.user.pk and can_contribute_gallery(entry.gallery, request.user))):
        raise Http404
    entry.delete()
    messages.success(request,_('Pieza retirada de la galería. Su registro personal sigue intacto.'))
    return redirect('gallery_manage',pk=pk)

