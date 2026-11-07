from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext
from django.utils.formats import date_format, number_format
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from .forms import ProgressForm
from .models import Piece, Progress, GlazeUse
from .services import save_photos
from .permissions import can_read


def sync_stage(piece):
    latest = piece.progress.first()
    piece.stage = latest.stage if latest else Piece.Stage.PROCESS
    piece.save(update_fields=['stage','updated_at'])


@login_required
@require_http_methods(['GET','POST'])
def progress_edit(request, pk, event_id=None):
    piece = get_object_or_404(Piece,pk=pk,owner=request.user)
    event = get_object_or_404(Progress,pk=event_id,piece=piece) if event_id else None
    form = ProgressForm(request.POST or None,request.FILES or None,instance=event,initial={'stage':piece.stage} if not event else None)
    back = reverse('piece',args=[pk])
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            piece = get_object_or_404(Piece.objects.select_for_update(),pk=pk,owner=request.user)
            saved = form.save(commit=False)
            saved.piece = piece
            saved.save()
            save_photos(form.cleaned_data['photos'],piece=piece,progress=saved)
            sync_stage(piece)
        messages.success(request,_('Avance actualizado.') if event else _('Avance añadido.'))
        return redirect(back)
    return render(request,'form.html',{
        'title':_('Editar avance') if event else _('Añadir avance'),'subtitle':piece.name,
        'section':'pieces','form':form,'back_url':back,
        'existing_photos':event.photos.all() if event else [],
        'photo_manage_url':reverse('photos_manage',kwargs={'kind':'piece','pk':pk}),
    })


@login_required
@require_http_methods(['GET','POST'])
def remove(request, pk, record_id, kind):
    piece = get_object_or_404(Piece,pk=pk,owner=request.user)
    model = Progress if kind=='progress' else GlazeUse
    record = get_object_or_404(model,pk=record_id,piece=piece)
    back = reverse('piece',args=[pk])
    if request.method=='POST' and request.POST.get('confirm_delete')=='yes':
        with transaction.atomic():
            piece = get_object_or_404(Piece.objects.select_for_update(),pk=pk,owner=request.user)
            record = get_object_or_404(model,pk=record_id,piece=piece)
            record.delete()
            if kind=='progress':
                sync_stage(piece)
            else:
                piece.save(update_fields=['updated_at'])
        messages.success(request,_('Avance eliminado.') if kind=='progress' else _('Uso de material eliminado.'))
        return redirect(back)
    message = (_('Se eliminará el avance, pero sus fotos se conservarán en la pieza. La etapa se actualizará según el último avance restante; sin avances volverá a «En proceso».') if kind=='progress' else _('Se eliminará únicamente este registro de aplicación. El material y su receta se conservan en la biblioteca.'))
    record_label = f'{record.get_stage_display()} · {date_format(record.date, "SHORT_DATE_FORMAT")}' if kind=='progress' else (record.glaze.name if can_read(record.glaze,request.user) else _('Material no disponible'))
    record_note = record.notes if kind=='progress' else ' · '.join(str(value) for value in [ngettext('%(counter)s capa','%(counter)s capas',record.layers) % {'counter':record.layers} if record.layers else '',f'{number_format(record.grams)} g' if record.grams is not None else '',record.zone,record.method] if value)
    return render(request,'confirm_delete.html',{
        'title':_('Eliminar avance') if kind=='progress' else _('Eliminar uso de material'),
        'section':'pieces','item_name':piece.name,'message':message,'back_url':back,
        'record_label':record_label,'record_note':record_note,
        'confirmation_error':request.method=='POST',
    },status=400 if request.method=='POST' else 200)
