from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from .forms import PiecePresentationForm
from .models import Gallery, GalleryEntry, Piece, PiecePresentation
from .permissions import can_contribute_gallery


@login_required
@require_http_methods(['GET', 'POST'])
def edit(request, pk, gallery_id=None):
    piece = get_object_or_404(Piece, pk=pk, owner=request.user)
    gallery = get_object_or_404(Gallery, pk=gallery_id) if gallery_id else None
    if gallery and not can_contribute_gallery(gallery, request.user):
        raise Http404
    presentation = PiecePresentation.objects.filter(piece=piece).first()
    initial = {'title': piece.name, 'photos': [piece.cover.pk] if piece.cover else []}
    form = PiecePresentationForm(request.POST if request.method == 'POST' else None,
                                 instance=presentation, initial=initial if not presentation else None, piece=piece)
    if request.method == 'POST' and form.is_valid():
        if request.POST.get('intent') == 'publish' and not form.cleaned_data['photos']:
            form.add_error('photos', _('Selecciona al menos una foto para publicar en Inspiración.'))
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            Piece.objects.select_for_update().get(pk=piece.pk)
            saved = form.save(commit=False)
            # Concurrent editors may have created or published it since GET.
            current = PiecePresentation.objects.select_for_update().filter(piece=piece).first()
            if current:
                saved.pk = current.pk
                saved.published = current.published
                saved.published_at = current.published_at
            if saved.published and not form.cleaned_data['photos']:
                form.add_error('photos', _('Retira la publicación antes de quitar todas las fotos.'))
            else:
                saved.needs_review = False
                if request.POST.get('intent') == 'publish':
                    saved.published = True
                    saved.published_at = saved.published_at or timezone.now()
                saved.save()
                form.save_m2m()
                if gallery:
                    Gallery.objects.select_for_update().get(pk=gallery.pk)
                    GalleryEntry.objects.get_or_create(gallery=gallery, piece=piece, defaults={'title': saved.title})
                messages.success(request, _('Pieza publicada en Inspiración.') if request.POST.get('intent') == 'publish' else _('Presentación guardada.'))
                return redirect('gallery_manage', pk=gallery.pk) if gallery else redirect('presentation_edit', pk=piece.pk)
    selected = {str(value) for value in (form['photos'].value() or [])}
    return render(request, 'presentation_form.html', {
        'title': _('Presentación pública'), 'section': 'pieces', 'piece': piece, 'selected_piece': piece,
        'form': form, 'presentation': presentation, 'gallery': gallery,
        'gallery_contains_piece': bool(gallery and piece.gallery_entries.filter(gallery=gallery).exists()),
        'back_url': reverse('gallery_manage', args=[gallery.pk]) if gallery else reverse('piece', args=[piece.pk]),
        'photo_choices': [{'photo': photo, 'selected': str(photo.pk) in selected} for photo in piece.photos.all()],
        'legacy_entries': piece.gallery_entries.all() if presentation and presentation.needs_review else [],
    })


@login_required
@require_POST
def publication(request, pk):
    if request.POST.get('action') not in ('publish', 'unpublish'):
        return HttpResponseBadRequest(_('Acción no válida.'))
    with transaction.atomic():
        piece = get_object_or_404(Piece.objects.select_for_update(), pk=pk, owner=request.user)
        presentation = PiecePresentation.objects.select_for_update().filter(piece=piece).first()
        if request.POST['action'] == 'publish':
            if not presentation or not presentation.title.strip() or not presentation.photos.exists() or presentation.needs_review:
                messages.error(request, _('Revisa la presentación y selecciona al menos una foto antes de publicar.'))
                return redirect('presentation_edit', pk=pk)
            presentation.published = True
            presentation.published_at = presentation.published_at or timezone.now()
            presentation.save(update_fields=['published', 'published_at'])
            messages.success(request, _('Pieza publicada en Inspiración.'))
        elif presentation:
            presentation.published = False
            presentation.save(update_fields=['published'])
            messages.success(request, _('Pieza retirada de Inspiración. Sus galerías se conservan.'))
    return redirect('presentation_edit', pk=pk)


@require_http_methods(['GET'])
def inspiration(request):
    presentations = PiecePresentation.objects.filter(published=True, published_at__isnull=False, photos__isnull=False).distinct()
    cursor = request.GET.get('cursor')
    if cursor:
        try:
            date, pk = signing.loads(cursor, salt='inspiration')
            date = parse_datetime(date)
            if date is None or timezone.is_naive(date):
                raise ValueError
            pk = int(pk)
        except (signing.BadSignature, ValueError, TypeError):
            return HttpResponseBadRequest(_('No se pudo cargar esta página. Vuelve a abrir Inspiración.'))
        presentations = presentations.filter(Q(published_at__lt=date) | Q(published_at=date, pk__lt=pk))
    batch = list(presentations.select_related('piece__owner').prefetch_related('photos').order_by('-published_at', '-pk')[:25])
    more = len(batch) > 24
    batch = batch[:24]
    next_url = ''
    if more:
        last = batch[-1]
        token = signing.dumps([last.published_at.isoformat(), last.pk], salt='inspiration')
        from urllib.parse import urlencode
        next_url = reverse('inspiration') + '?' + urlencode({'cursor': token})
    return render(request, 'partials/inspiration_batch.html' if request.headers.get('X-Inspiration-Batch') == '1' else 'inspiration.html', {
        'title': _('Inspiración'), 'section': 'inspiration', 'presentations': batch, 'next_url': next_url,
    })
