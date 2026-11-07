document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-photo-order]').forEach(form => {
    const list = form.querySelector('[data-photo-order-list]');
    const status = form.querySelector('[data-order-status]');
    const cards = () => [...list.querySelectorAll('[data-photo-card]')];
    const initialOrder = cards().map(card => card.querySelector('input[name="order"]').value).join(',');
    const refresh = () => {
      const items = cards();
      items.forEach((card,index) => {
        card.querySelector('[data-photo-number]').textContent = interpolate(gettext('Foto %(value0)s'),{value0:index+1},true);
        const image = card.querySelector('img');
        image.alt = interpolate(gettext('%(value0)s · Foto %(value1)s'),{value0:image.dataset.photoBase,value1:index+1},true);
        card.querySelector('[data-photo-action="up"]').disabled = index===0;
        card.querySelector('[data-photo-action="down"]').disabled = index===items.length-1;
        card.querySelector('[data-photo-action="cover"]').disabled = index===0;
        card.querySelector('[data-photo-action="up"]').setAttribute('aria-label',interpolate(gettext('Mover foto %(value0)s antes'),{value0:index+1},true));
        card.querySelector('[data-photo-action="down"]').setAttribute('aria-label',interpolate(gettext('Mover foto %(value0)s después'),{value0:index+1},true));
      });
      status.textContent = items.map(card => card.querySelector('input[name="order"]').value).join(',') === initialOrder ? '' : gettext('Cambios pendientes de guardar');
      form.dispatchEvent(new Event('input', {bubbles:true}));
    };
    form.addEventListener('click', event => {
      const button = event.target.closest('[data-photo-action]');
      if (!button) return;
      event.preventDefault();
      const card = button.closest('[data-photo-card]');
      const action = button.dataset.photoAction;
      if (action==='up' && card.previousElementSibling) list.insertBefore(card,card.previousElementSibling);
      if (action==='down' && card.nextElementSibling) list.insertBefore(card.nextElementSibling,card);
      if (action==='cover') list.prepend(card);
      refresh();
      // A move may disable its button; retain focus on the card's preview.
      if (button.disabled) card.querySelector('a').focus();
      else button.focus();
    });
    let dragged;
    list.addEventListener('dragstart', event => {
      if (event.target.closest('button')) { event.preventDefault(); return; }
      dragged = event.target.closest('[data-photo-card]');
      if (!dragged) return;
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain',dragged.querySelector('input[name="order"]').value);
      dragged.classList.add('is-dragging');
    });
    list.addEventListener('dragover', event => {
      if (!dragged) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
    });
    list.addEventListener('drop', event => {
      if (!dragged) return;
      event.preventDefault();
      const target = event.target.closest('[data-photo-card]');
      if (target && target!==dragged) {
        const items = cards();
        list.insertBefore(dragged,items.indexOf(dragged)<items.indexOf(target)?target.nextElementSibling:target);
        refresh();
      }
    });
    list.addEventListener('dragend', () => {
      dragged?.classList.remove('is-dragging');
      dragged = null;
    });
  });

  let viewer;
  let items = [];
  let index = 0;
  let zoom = 1;
  let trigger;
  let previousOverflow;
  let previousScrollX, previousScrollY;
  const makeViewer = () => {
    viewer = document.createElement('dialog');
    viewer.className = 'photo-viewer';
    viewer.setAttribute('aria-label',gettext('Visor de fotografías'));
    viewer.innerHTML = `<div class="photo-viewer-layout">
      <header class="photo-viewer-header"><span data-viewer-caption></span><button type="button" data-viewer-close>×</button></header>
      <div class="photo-viewer-stage" data-viewer-stage><div class="photo-viewer-canvas"><img data-viewer-image alt="" draggable="false"></div><p data-viewer-error role="status" hidden></p></div>
      <div class="photo-viewer-toolbar"><div class="photo-viewer-navigation"><button type="button" data-viewer-prev>←</button><span data-viewer-position aria-live="polite"></span><button type="button" data-viewer-next>→</button></div>
      <div class="photo-viewer-zoom"><button type="button" data-viewer-minus>−</button><button type="button" data-viewer-reset>100 %</button><button type="button" data-viewer-plus>+</button></div></div>
    </div>`;
    viewer.querySelector('[data-viewer-close]').setAttribute('aria-label', gettext('Cerrar visor'));
    viewer.querySelector('[data-viewer-prev]').setAttribute('aria-label', gettext('Foto anterior'));
    viewer.querySelector('[data-viewer-next]').setAttribute('aria-label', gettext('Foto siguiente'));
    viewer.querySelector('[data-viewer-minus]').setAttribute('aria-label', gettext('Alejar'));
    viewer.querySelector('[data-viewer-reset]').setAttribute('aria-label', gettext('Restablecer zoom'));
    viewer.querySelector('[data-viewer-plus]').setAttribute('aria-label', gettext('Acercar'));
    viewer.querySelector('[data-viewer-error]').textContent = gettext('No se puede cargar esta foto.');
    document.body.append(viewer);
    const close = () => viewer.close();
    viewer.querySelector('[data-viewer-close]').addEventListener('click',close);
    viewer.addEventListener('close', () => {
      document.documentElement.style.overflow = previousOverflow;
      trigger?.focus({preventScroll:true});
      window.scrollTo({left:previousScrollX, top:previousScrollY, behavior:'instant'});
    });
    const stage = viewer.querySelector('[data-viewer-stage]');
    const image = viewer.querySelector('[data-viewer-image]');
    image.addEventListener('load', () => { image.hidden=false; fit(); });
    image.addEventListener('error', () => { image.hidden=true; viewer.querySelector('[data-viewer-error]').hidden=false; });
    viewer.querySelector('[data-viewer-prev]').addEventListener('click', () => show(index-1));
    viewer.querySelector('[data-viewer-next]').addEventListener('click', () => show(index+1));
    viewer.querySelector('[data-viewer-plus]').addEventListener('click', () => changeZoom(zoom+.5));
    viewer.querySelector('[data-viewer-minus]').addEventListener('click', () => changeZoom(zoom-.5));
    viewer.querySelector('[data-viewer-reset]').addEventListener('click', () => changeZoom(1));
    image.addEventListener('dblclick', () => changeZoom(zoom===1?2:1));
    stage.addEventListener('wheel',event => {
      if (event.ctrlKey) { event.preventDefault(); changeZoom(zoom+(event.deltaY<0?.25:-.25)); }
    },{passive:false});
    viewer.addEventListener('keydown',event => {
      if (event.key==='ArrowLeft') { event.preventDefault(); show(index-1); }
      if (event.key==='ArrowRight') { event.preventDefault(); show(index+1); }
      if (event.key==='+' || event.key==='=') { event.preventDefault(); changeZoom(zoom+.5); }
      if (event.key==='-') { event.preventDefault(); changeZoom(zoom-.5); }
      if (event.key==='0') { event.preventDefault(); changeZoom(1); }
    });
    window.addEventListener('resize', () => { if (viewer.open) fit(); });
  };
  const fit = () => {
    const image = viewer.querySelector('[data-viewer-image]');
    const stage = viewer.querySelector('[data-viewer-stage]');
    if (!image.naturalWidth) return;
    const ratio = Math.max(.01,Math.min((stage.clientWidth-32)/image.naturalWidth,(stage.clientHeight-32)/image.naturalHeight));
    image.style.width = `${image.naturalWidth*ratio*zoom}px`;
    image.style.height = `${image.naturalHeight*ratio*zoom}px`;
    viewer.querySelector('[data-viewer-reset]').textContent = `${Math.round(zoom*100)} %`;
    viewer.querySelector('[data-viewer-minus]').disabled = zoom<=1;
    viewer.querySelector('[data-viewer-plus]').disabled = zoom>=4;
  };
  const changeZoom = value => {
    zoom = Math.max(1,Math.min(4,value));
    fit();
  };
  const show = requested => {
    index = (requested+items.length)%items.length;
    zoom = 1;
    const image = viewer.querySelector('[data-viewer-image]');
    const item = items[index];
    viewer.querySelector('[data-viewer-error]').hidden = true;
    image.hidden = true;
    image.alt = item.alt;
    image.src = item.url;
    viewer.querySelector('[data-viewer-caption]').textContent = item.alt;
    viewer.querySelector('[data-viewer-position]').textContent = `${index+1} / ${items.length}`;
    viewer.querySelector('[data-viewer-prev]').disabled = items.length<2;
    viewer.querySelector('[data-viewer-next]').disabled = items.length<2;
    viewer.querySelector('[data-viewer-reset]').textContent = '100 %';
    viewer.querySelector('[data-viewer-stage]').scrollTo(0,0);
    if (image.complete && image.naturalWidth) { image.hidden=false; fit(); }
  };
  document.addEventListener('click',event => {
    const anchor = event.target.closest('a[data-lightbox]');
    if (!anchor || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button!==0 || !window.HTMLDialogElement) return;
    event.preventDefault();
    const group = anchor.closest('[data-lightbox-group],.photo-strip,.resource-reference-grid,.resource-existing-photos') || anchor.parentElement;
    const links = [...group.querySelectorAll('a[data-lightbox]')];
    const unique = new Map();
    links.forEach(link => unique.set(link.href,{url:link.href,alt:link.querySelector('img')?.alt || gettext('Fotografía')}));
    items = [...unique.values()];
    if (!items.length) return;
    if (!viewer) makeViewer();
    trigger = anchor;
    previousOverflow = document.documentElement.style.overflow;
    previousScrollX = window.scrollX;
    previousScrollY = window.scrollY;
    document.documentElement.style.overflow = 'hidden';
    viewer.showModal();
    show(items.findIndex(item=>item.url===anchor.href));
  });
});
