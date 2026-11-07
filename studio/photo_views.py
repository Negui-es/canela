from django.utils.translation import gettext_lazy as _
import uuid
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from .forms import PhotosField
from .models import Piece, Mold, Glaze, Sample, Photo
from .services import save_photos, schedule_photo_cleanup
from .permissions import editable_materials


class UploadPhotosForm(forms.Form):
    photos = PhotosField(label=_('Añadir fotos'))

    def clean_photos(self):
        photos = self.cleaned_data['photos']
        if not photos:
            raise forms.ValidationError(_('Selecciona al menos una fotografía.'))
        return photos


def collection(request, kind, pk, *, lock=False):
    models = {'piece':Piece,'mold':Mold,'glaze':Glaze,'sample':Sample}
    model = models.get(kind)
    if not model:
        raise Http404
    queryset = model.objects.select_for_update() if lock else model.objects.all()
    if kind in ('glaze', 'mold'):
        queryset = queryset.filter(pk__in=editable_materials(request.user, model).values('pk'))
    elif kind == 'sample':
        queryset = queryset.filter(glaze__in=editable_materials(request.user))
    else:
        queryset = queryset.filter(owner=request.user)
    parent = get_object_or_404(queryset, pk=pk)
    resource = parent.glaze if kind=='sample' else parent
    back = reverse('glaze' if kind=='sample' else kind, args=[resource.pk])
    section = {'piece':'pieces','mold':'molds','glaze':'glazes','sample':'glazes'}[kind]
    return parent, resource, back, section


def photo_collection(photo):
    for kind in ('piece','mold','glaze','sample'):
        parent_id = getattr(photo, kind+'_id')
        if parent_id:
            return kind, parent_id
    raise Http404


def touch(resource):
    type(resource).objects.filter(pk=resource.pk).update(updated_at=timezone.now())


@login_required
@require_http_methods(['GET','POST'])
def manage(request, kind, pk):
    parent, resource, back, section = collection(request, kind, pk)
    uploading = request.method=='POST' and 'upload' in request.POST
    form = UploadPhotosForm(request.POST if uploading else None, request.FILES if uploading else None)
    if uploading and form.is_valid():
        with transaction.atomic():
            parent, resource, _unused, _unused = collection(request, kind, pk, lock=True)
            save_photos(form.cleaned_data['photos'], **{kind:parent})
            touch(resource)
        messages.success(request,_('Fotografías añadidas.'))
        return redirect('photos_manage',kind=kind,pk=pk)
    if request.method=='POST' and not uploading:
        with transaction.atomic():
            parent, resource, _unused, _unused = collection(request, kind, pk, lock=True)
            photos = list(parent.photos.all())
            try:
                order = [uuid.UUID(value) for value in request.POST.getlist('order')]
                if len(order)!=len(photos) or set(order)!={photo.pk for photo in photos}:
                    raise ValueError
                actions = [action for action in ('up','down','cover','save_order') if action in request.POST]
                if len(actions)!=1:
                    raise ValueError
                action = actions[0]
                if action!='save_order':
                    selected = uuid.UUID(request.POST[action])
                    index = order.index(selected)
                    if action=='cover':
                        order.insert(0,order.pop(index))
                    elif action=='up' and index>0:
                        order[index-1],order[index] = order[index],order[index-1]
                    elif action=='down' and index<len(order)-1:
                        order[index+1],order[index] = order[index],order[index+1]
            except (ValueError,TypeError):
                return HttpResponseBadRequest(_('No se pudo guardar el orden. Recarga la página e inténtalo de nuevo.'))
            positions = {photo_id:index for index,photo_id in enumerate(order)}
            for photo in photos:
                photo.position = positions[photo.pk]
            Photo.objects.bulk_update(photos,['position'])
            touch(resource)
        messages.success(request,_('Orden y portada guardados.'))
        return redirect('photos_manage',kind=kind,pk=pk)
    return render(request,'photos_manage.html',{
        'title':_('Gestionar fotos'),'section':section,'resource':resource,'kind':kind,'parent':parent,
        'photos':parent.photos.select_related('progress'),'form':form,'back_url':back,'uploading':uploading,
    }, status=400 if uploading else 200)


@login_required
@require_http_methods(['GET','POST'])
def remove(request, pk):
    photo = get_object_or_404(Photo,pk=pk)
    kind, parent_id = photo_collection(photo)
    _unused, resource, _unused, section = collection(request,kind,parent_id)
    back = reverse('photos_manage',kwargs={'kind':kind,'pk':parent_id})
    if request.method=='POST' and request.POST.get('confirm_delete')=='yes':
        with transaction.atomic():
            collection(request,kind,parent_id,lock=True)
            photo = get_object_or_404(Photo,pk=pk,**{kind+'_id':parent_id})
            photo.delete()
            if kind == 'piece':
                from .models import PiecePresentation
                PiecePresentation.objects.filter(piece_id=parent_id, published=True, photos__isnull=True).update(published=False)
            schedule_photo_cleanup([photo])
            touch(resource)
        messages.success(request,_('Fotografía eliminada.'))
        return redirect(back)
    return render(request,'confirm_delete.html',{
        'title':_('Eliminar fotografía'),'section':section,'back_url':back,'item_name':resource.name,
        'photo':photo,'message':_('Se eliminará esta foto de la ficha, de su presentación y de las galerías. Si era la última foto publicada, la pieza se retirará de Inspiración. Esta acción es definitiva.'),
        'confirmation_error':request.method=='POST',
    },status=400 if request.method=='POST' else 200)
