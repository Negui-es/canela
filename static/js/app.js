document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-batch-calculator]').forEach(widget => {
    const input = widget.querySelector('[data-batch-amount]');
    const error = widget.querySelector('[data-batch-error]');
    const update = () => {
      const amount = input.valueAsNumber;
      const valid = input.value !== '' && Number.isFinite(amount) && input.validity.valid;
      error.hidden = valid;
      input.setAttribute('aria-invalid', String(!valid));
      widget.querySelectorAll('[data-batch-result]').forEach(cell => {
        cell.textContent = valid ? (amount * Number(cell.dataset.percent) / 100).toLocaleString(document.documentElement.lang, {maximumFractionDigits:2}) + ' g' : '—';
      });
    };
    input.addEventListener('input', update);
    update();
  });
  document.querySelectorAll('[data-sharing-picker]').forEach(picker => {
    const status = picker.querySelector('[data-sharing-status]');
    const update = () => {
      const count = picker.querySelectorAll('input:checked').length;
      status.textContent = count ? interpolate(ngettext('Compartida con %(count)s grupo','Compartida con %(count)s grupos',count),{count},true) : status.dataset.sharingEmpty;
    };
    picker.addEventListener('change',update);
    update();
  });
  const notifications = root => {
    root.querySelectorAll('[data-notification]:not([data-ready])').forEach(notification => {
      notification.dataset.ready = 'true';
      let remaining = 4000;
      let started = 0;
      let timer;
      let closing = false;
      const automatic = notification.dataset.autoclose === 'true';
      const dismiss = () => {
        if (closing) return;
        closing = true;
        clearTimeout(timer);
        notification.classList.add('is-leaving');
        setTimeout(() => {
          const stack = notification.parentElement;
          notification.remove();
          if (stack && !stack.children.length) stack.remove();
        }, 170);
      };
      const pause = () => {
        if (!timer) return;
        clearTimeout(timer);
        timer = null;
        remaining = Math.max(0, remaining - (performance.now() - started));
      };
      const resume = () => {
        if (!automatic || closing || timer || notification.matches(':hover') || notification.contains(document.activeElement)) return;
        started = performance.now();
        timer = setTimeout(dismiss, remaining);
      };
      notification.querySelector('[data-dismiss-notification]').addEventListener('click', dismiss);
      notification.addEventListener('mouseenter', pause);
      notification.addEventListener('mouseleave', resume);
      notification.addEventListener('focusin', pause);
      notification.addEventListener('focusout', () => setTimeout(resume, 0));
      resume();
    });
  };
  notifications(document);
  document.querySelectorAll('[data-photo-gallery]').forEach(gallery => {
    const track = gallery.querySelector('[data-photo-track]');
    const controls = gallery.querySelector('[data-photo-controls]');
    if (!controls) return;
    const slides = [...track.children];
    const previous = controls.querySelector('[data-photo-prev]');
    const next = controls.querySelector('[data-photo-next]');
    const update = () => {
      const index = Math.max(0, Math.min(slides.length - 1, Math.round(track.scrollLeft / (track.clientWidth || 1))));
      controls.querySelector('[data-photo-position]').textContent = `${index + 1} / ${slides.length}`;
      previous.disabled = index === 0;
      next.disabled = index === slides.length - 1;
    };
    const move = direction => track.scrollBy({left:direction * track.clientWidth,
      behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
    previous.addEventListener('click', () => move(-1));
    next.addEventListener('click', () => move(1));
    track.addEventListener('keydown', event => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
        event.preventDefault();
        move(event.key === 'ArrowLeft' ? -1 : 1);
      }
    });
    track.addEventListener('scroll', update, {passive:true});
    window.addEventListener('resize', update);
    controls.hidden = false;
    update();
  });
  document.addEventListener('htmx:afterSwap', () => notifications(document));
  window.addEventListener('pageshow', event => {
    if (event.persisted) document.querySelectorAll('[data-notification][data-autoclose="true"]').forEach(node => node.remove());
  });
  document.querySelectorAll('[data-uploader]').forEach(widget => {
    const input = widget.querySelector('[data-photo-input]');
    const camera = widget.querySelector('[data-camera-input]');
    const zone = widget.querySelector('[data-dropzone]');
    const previews = widget.querySelector('[data-upload-previews]');
    const error = widget.querySelector('[data-upload-error]');
    if (!input || !window.DataTransfer) return;
    widget.dataset.enhanced = 'true';
    let files = [];
    let urls = [];
    const clearUrls = () => { urls.forEach(url => URL.revokeObjectURL(url)); urls = []; };
    const render = () => {
      clearUrls();
      const transfer = new DataTransfer();
      files.forEach(file => transfer.items.add(file));
      input.files = transfer.files;
      input.dispatchEvent(new Event('input', {bubbles:true}));
      widget.querySelector('[data-photo-count]').textContent = files.length + ' / 4';
      previews.replaceChildren();
      files.forEach((file, index) => {
        const card = document.createElement('div');
        card.className = 'upload-preview';
        const img = document.createElement('img');
        img.alt = file.name;
        img.src = URL.createObjectURL(file);
        urls.push(img.src);
        const info = document.createElement('div');
        info.className = 'upload-preview-info';
        const name = document.createElement('strong');
        name.textContent = file.name;
        const size = document.createElement('small');
        size.textContent = file.size < 1024 * 1024
          ? Math.max(1, Math.round(file.size / 1024)).toLocaleString(document.documentElement.lang) + ' KB'
          : (file.size / 1024 / 1024).toLocaleString(document.documentElement.lang, {maximumFractionDigits:1}) + ' MB';
        info.append(name, size);
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'upload-remove';
        remove.textContent = '×';
        remove.setAttribute('aria-label', interpolate(gettext('Quitar %(name)s'), {name:file.name}, true));
        remove.addEventListener('click', () => {
          files.splice(index, 1);
          error.hidden = true;
          render();
          const remaining = previews.querySelectorAll('.upload-remove');
          (remaining[Math.min(index, remaining.length - 1)] || widget.querySelector('[data-choose]')).focus();
        });
        card.append(img, info, remove);
        previews.append(card);
      });
    };
    const add = incoming => {
      const errors = [];
      for (const file of Array.from(incoming)) {
        if (!['image/jpeg','image/png','image/webp'].includes(file.type) && !(file.type === '' && /\.(jpe?g|png|webp)$/i.test(file.name))) {
          errors.push(gettext('Usa imágenes JPG, PNG o WebP.'));
          continue;
        }
        if (file.size > 5 * 1024 * 1024) { errors.push(gettext('Cada foto debe ocupar menos de 5 MB.')); continue; }
        if (files.some(existing => existing.name === file.name && existing.size === file.size && existing.lastModified === file.lastModified)) continue;
        if (files.length >= 4) { errors.push(gettext('Puedes subir hasta 4 fotos cada vez.')); continue; }
        files.push(file);
      }
      error.textContent = [...new Set(errors)].join(' ');
      error.hidden = errors.length === 0;
      render();
    };
    widget.querySelector('[data-choose]').addEventListener('click', () => input.click());
    widget.querySelector('[data-camera]').addEventListener('click', () => camera.click());
    input.addEventListener('change', () => add(input.files));
    camera.addEventListener('change', () => { add(camera.files); camera.value = ''; });
    let dragDepth = 0;
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(type => zone.addEventListener(type, event => {
      event.preventDefault();
      event.stopPropagation();
      if (type === 'dragenter') dragDepth++;
      if (type === 'dragleave') dragDepth = Math.max(0, dragDepth - 1);
      if (type === 'drop') { dragDepth = 0; add(event.dataTransfer.files); }
      zone.classList.toggle('is-dragging', dragDepth > 0);
      if (type === 'dragover') event.dataTransfer.dropEffect = 'copy';
    }));
    window.addEventListener('pagehide', clearUrls, {once:true});
  });
  document.querySelectorAll('[data-gallery-settings]').forEach(form => {
    const update = () => {
      const inWorkshop = Boolean(form.querySelector('[name="workshop"]')?.value);
      const privateChoice = form.querySelector('[name="audience"][value="private"]');
      if (privateChoice) {
        privateChoice.disabled = inWorkshop;
        privateChoice.closest('label').hidden = inWorkshop;
        if (inWorkshop && privateChoice.checked) form.querySelector('[name="audience"][value="group"]').checked = true;
      }
      const audience = form.querySelector('[name="audience"]:checked')?.value;
      form.querySelector('[data-gallery-groups]').hidden = audience !== 'group' || inWorkshop;
      form.querySelector('[data-gallery-public]').hidden = audience !== 'public';
    };
    form.addEventListener('change', update);
    update();
  });
  document.querySelectorAll('[data-gallery-presentation]').forEach(form => {
    const choices = [...form.querySelectorAll('[data-gallery-photo-choice]')];
    const update = () => {
      const count = choices.filter(input => input.checked).length;
      const summary = form.querySelector('[data-gallery-photo-count]');
      if (summary) summary.textContent = interpolate(ngettext('%(count)s foto seleccionada','%(count)s fotos seleccionadas',count),{count},true);
    };
    form.querySelectorAll('[data-select-photos]').forEach(button => button.addEventListener('click', () => {
      choices.forEach(input => { input.checked = button.dataset.selectPhotos === 'all'; });
      update();
    }));
    form.addEventListener('change', update);
    update();
  });
  document.querySelectorAll('[data-share-link]').forEach(widget => {
    widget.querySelector('[data-copy-gallery]').addEventListener('click', async () => {
      const input = widget.querySelector('input');
      try {
        await navigator.clipboard.writeText(input.value);
        widget.querySelector('[data-copy-status]').textContent = gettext('Enlace copiado');
      } catch {
        input.focus(); input.select();
        widget.querySelector('[data-copy-status]').textContent = gettext('Selecciona y copia el enlace.');
      }
    });
  });
  document.querySelectorAll('[data-glaze-picker]').forEach(picker => {
    const options = [...picker.querySelectorAll('[data-glaze-name]')];
    const search = picker.querySelector('[data-glaze-search]');
    const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase(document.documentElement.lang);
    const updateCount = () => {
      const count = picker.querySelectorAll('input[type="checkbox"]:checked').length;
      picker.querySelector('[data-glaze-count]').textContent = count
        ? interpolate(ngettext('%(count)s material seleccionado','%(count)s materiales seleccionados',count),{count},true)
        : gettext('Sin materiales asignados. Puedes añadirlos más adelante.');
    };
    search.addEventListener('input', () => {
      const query = normalize(search.value.trim());
      options.forEach(option => { option.hidden = !normalize(option.dataset.glazeName).includes(query); });
      picker.querySelector('[data-glaze-empty]').hidden = options.some(option => !option.hidden);
    });
    picker.addEventListener('change', updateCount);
    updateCount();
  });
  document.querySelectorAll('[data-resource-kind="glaze"]').forEach(form => {
    const updateKind = () => {
      const commercial = form.querySelector('input[name="kind"]:checked')?.value === 'commercial';
      form.querySelector('[data-commercial-field]').hidden = !commercial;
      const category = form.querySelector('input[name="material_type"]:checked')?.value || 'glaze';
      form.querySelectorAll('[data-material-fields]').forEach(group => {
        const active = group.dataset.materialFields.split(' ').includes(category);
        group.hidden = !active;
        group.querySelectorAll('input,select,textarea').forEach(input => { input.disabled = !active; });
      });
      form.querySelector('[name="name"]').placeholder = {
        glaze: gettext('Por ejemplo, blanco avena'),
        engobe: gettext('Por ejemplo, engobe azul'),
        clay: gettext('Por ejemplo, gres blanco con chamota')
      }[category];
    };
    form.querySelectorAll('input[name="kind"],input[name="material_type"],select[name="group"]').forEach(input => input.addEventListener('change', updateKind));
    updateKind();
  });
  document.querySelectorAll('[data-resource-kind]').forEach(form => {
    const select = form.querySelector('select[name="group"]');
    if (!select) return;
    const updateOwnership = () => {
      const groupOwned = Boolean(select.value);
      form.querySelector('[data-group-ownership]').hidden = !groupOwned;
      document.querySelector('[data-personal-privacy]').hidden = groupOwned;
      document.querySelector('[data-group-privacy]').hidden = !groupOwned;
      form.querySelectorAll('.material-category-option[href]').forEach(link => {
        const url = new URL(link.href);
        if (select.value) url.searchParams.set('group', select.value);
        else url.searchParams.delete('group');
        link.href = url.pathname + url.search;
      });
    };
    select.addEventListener('change', updateOwnership);
    updateOwnership();
  });
  document.querySelectorAll('select[name="glaze"]').forEach(select => {
    const layers = select.form.querySelector('[data-coating-layers]');
    if (!layers) return;
    const update = () => {
      const clay = select.selectedOptions[0]?.dataset.materialType === 'clay';
      layers.disabled = clay;
      layers.closest('.field').hidden = clay;
    };
    select.addEventListener('change', update);
    update();
  });
});
