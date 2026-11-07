document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-recipe-editor]').forEach(editor => {
    const source = editor.querySelector('textarea');
    const list = editor.querySelector('[data-recipe-rows]');
    const add = editor.querySelector('[data-recipe-add]');
    const total = editor.querySelector('[data-recipe-total]');
    const initial = source.value.trim() ? source.value.trim().split('\n').map(line => {
      const separator = line.lastIndexOf(';');
      return separator < 1 ? null : [line.slice(0, separator).trim(), line.slice(separator + 1).trim().replace(',', '.')];
    }) : [['', '']];
    // Malformed legacy input stays editable in its original form.
    if (initial.some(row => !row || !Number.isFinite(Number(row[1])))) return;
    source.dataset.recipeSource = '';
    source.required = false;
    source.hidden = true;
    editor.querySelector('[data-recipe-raw]').hidden = true;
    editor.querySelector('[data-recipe-raw-label]').hidden = true;
    editor.querySelector('[data-recipe-enhanced]').hidden = false;
    const rows = () => [...list.querySelectorAll('.recipe-ingredient-row')];
    const sync = (notify = true) => {
      const ingredients = rows();
      const sum = ingredients.reduce((value, row) => value + Math.round((Number(row.querySelector('[data-ingredient-percent]').value) || 0) * 1000), 0);
      const percentage = (sum / 1000).toLocaleString(document.documentElement.lang, {maximumFractionDigits:3});
      total.textContent = `${gettext('Total')}: ${percentage} %`;
      total.classList.toggle('is-complete', sum === 100000);
      total.classList.toggle('is-over', sum > 100000);
      ingredients.forEach(row => row.querySelector('[data-ingredient-percent]').setCustomValidity(''));
      ingredients[0].querySelector('[data-ingredient-percent]').setCustomValidity(sum === 100000 ? '' : gettext('Los porcentajes deben sumar 100 %.'));
      source.value = ingredients.filter(row => row.querySelector('[data-ingredient-name]').value.trim() || row.querySelector('[data-ingredient-percent]').value).map(row => row.querySelector('[data-ingredient-name]').value.trim() + '; ' + row.querySelector('[data-ingredient-percent]').value).join('\n');
      add.disabled = ingredients.length >= 50;
      ingredients.forEach((row, index) => {
        row.setAttribute('role', 'group');
        row.setAttribute('aria-label', `${gettext('Ingrediente')} ${index + 1}`);
        const remove = row.querySelector('[data-recipe-remove]');
        remove.disabled = ingredients.length === 1;
        remove.setAttribute('aria-label', `${gettext('Quitar ingrediente')}: ${row.querySelector('[data-ingredient-name]').value.trim() || index + 1}`);
      });
      if (notify) source.dispatchEvent(new Event('input', {bubbles:true}));
    };
    const addRow = (name = '', percentage = '', focus = true) => {
      const row = editor.querySelector('template').content.firstElementChild.cloneNode(true);
      row.querySelector('[data-ingredient-name]').value = name;
      row.querySelector('[data-ingredient-percent]').value = percentage === '' ? '' : String(Number(percentage));
      list.append(row);
      if (focus) row.querySelector('input').focus();
    };
    initial.forEach(([name, percentage]) => addRow(name, percentage, false));
    list.addEventListener('input', () => sync());
    list.addEventListener('click', event => {
      const button = event.target.closest('[data-recipe-remove]');
      if (!button || rows().length === 1) return;
      const row = button.closest('.recipe-ingredient-row');
      const next = row.nextElementSibling || row.previousElementSibling;
      row.remove();
      sync();
      next.querySelector('input').focus();
    });
    add.addEventListener('click', () => { if (rows().length < 50) { addRow(); sync(); } });
    source.form.addEventListener('submit', event => {
      sync(false);
      if (!source.form.checkValidity()) { event.preventDefault(); source.form.reportValidity(); }
    });
    sync(false);
    source.form.dispatchEvent(new Event('canela:form-ready'));
  });
});
