(() => {
  const form = document.querySelector('[data-presentation-editor]');
  if (!form) return;
  const update = event => {
    if (event?.target.name === 'cover' && event.target.value) {
      const checkbox = [...form.querySelectorAll('input[name="photos"]')].find(input => input.value === event.target.value);
      if (checkbox) checkbox.checked = true;
    }
    if (event?.target.name === 'photos' && !event.target.checked && form.elements.cover.value === event.target.value) {
      form.elements.cover.value = '';
      form.elements.cover.dispatchEvent(new Event('change', {bubbles:true}));
    }
    for (const name of ['title', 'description', 'technique', 'materials', 'dimensions', 'availability']) {
      form.querySelector(`[data-preview-${name}]`).textContent = form.elements[name].value;
    }
    const selected = [...form.querySelectorAll('input[name="photos"]:checked')];
    const cover = selected.find(input => input.value === form.elements.cover.value) || selected[0];
    const image = form.querySelector('[data-preview-cover]');
    image.hidden = !cover;
    form.querySelector('[data-preview-empty]').hidden = !!cover;
    if (cover) image.src = cover.closest('label').querySelector('img').src;
    else image.removeAttribute('src');
    const count = form.querySelector('[data-presentation-photo-count]');
    if (count) count.textContent = interpolate(ngettext('%(count)s foto seleccionada', '%(count)s fotos seleccionadas', selected.length), {count:selected.length}, true);
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
  update();
})();
