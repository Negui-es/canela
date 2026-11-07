/* Gallery selection keeps a native multiple select as the submitted value. */
(() => {
  'use strict';
  const normalize = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  let sequence = 0;
  function enhance(control) {
    if (control.dataset.enhanced) return;
    const select = control.querySelector('select[multiple]');
    if (!select) return;
    control.dataset.enhanced = 'true';
    const labels = control.dataset;
    const id = 'gallery-options-' + (++sequence);
    const chips = document.createElement('ul');
    chips.className = 'gallery-selection';
    chips.setAttribute('aria-label', labels.selectedLabel);
    const status = document.createElement('p');
    status.className = 'gallery-selection-status';
    status.setAttribute('role', 'status');
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'select-trigger gallery-add';
    trigger.textContent = '+ ' + labels.addLabel;
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', id);
    if (select.getAttribute('aria-describedby')) trigger.setAttribute('aria-describedby', select.getAttribute('aria-describedby'));
    if (select.getAttribute('aria-invalid')) trigger.setAttribute('aria-invalid', select.getAttribute('aria-invalid'));
    trigger.disabled = select.disabled;
    const menu = document.createElement('div');
    menu.className = 'select-menu gallery-menu';
    menu.hidden = true;
    menu.setAttribute('popover', 'manual');
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'select-search';
    search.placeholder = labels.searchLabel;
    search.setAttribute('aria-label', labels.searchLabel);
    search.setAttribute('role', 'combobox');
    search.setAttribute('aria-autocomplete', 'list');
    search.setAttribute('aria-controls', id);
    search.setAttribute('aria-expanded', 'false');
    const list = document.createElement('div');
    list.className = 'select-options';
    list.id = id;
    list.setAttribute('role', 'listbox');
    list.setAttribute('aria-label', labels.addLabel);
    const empty = document.createElement('p');
    empty.className = 'select-empty';
    empty.textContent = labels.emptyLabel;
    menu.append(search, list, empty);
    document.body.append(menu);
    control.append(chips, status, trigger);
    select.classList.add('select-native');
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    control.querySelector('.gallery-native-label').hidden = true;
    let rows = [], active = -1;
    const position = () => {
      const rect = trigger.getBoundingClientRect();
      const viewport = window.visualViewport;
      const top = viewport?.offsetTop || 0, left = viewport?.offsetLeft || 0;
      const width = viewport?.width || innerWidth, bottom = top + (viewport?.height || innerHeight);
      const below = bottom - rect.bottom - 18, above = rect.top - top - 18;
      const upwards = below < 210 && above > below;
      menu.style.width = Math.min(Math.max(rect.width, 280), width - 24) + 'px';
      menu.style.maxHeight = Math.max(90, Math.min(340, upwards ? above : below)) + 'px';
      const bounds = menu.getBoundingClientRect();
      menu.style.left = Math.max(left + 12, Math.min(rect.left, left + width - bounds.width - 12)) + 'px';
      menu.style.top = Math.max(top + 12, Math.min(upwards ? rect.top - bounds.height - 6 : rect.bottom + 6, bottom - bounds.height - 12)) + 'px';
    };
    const activate = (index, scroll = false) => {
      active = index;
      rows.forEach((row, i) => row.classList.toggle('is-active', i === index));
      if (rows[index]) {
        search.setAttribute('aria-activedescendant', rows[index].id);
        if (scroll) rows[index].scrollIntoView({block: 'nearest'});
      } else search.removeAttribute('aria-activedescendant');
    };
    const emit = () => {
      select.dispatchEvent(new Event('input', {bubbles: true}));
      select.dispatchEvent(new Event('change', {bubbles: true}));
    };
    const build = () => {
      list.replaceChildren();
      const query = normalize(search.value.trim());
      rows = [...select.options].filter(option => !option.selected && !option.disabled && !option.hidden && normalize(option.text).includes(query)).map(option => {
        const row = document.createElement('div');
        row.className = 'select-option';
        row.id = id + '-' + option.index;
        row.setAttribute('role', 'option');
        row.setAttribute('aria-selected', 'false');
        row.textContent = option.text;
        row.addEventListener('pointerdown', event => event.preventDefault());
        row.addEventListener('pointermove', () => activate(rows.indexOf(row)));
        row.addEventListener('click', () => {
          option.selected = true;
          search.value = '';
          emit();
          search.focus({preventScroll: true});
        });
        list.append(row);
        return row;
      });
      empty.hidden = rows.length > 0;
      activate(rows.length ? 0 : -1);
      if (!menu.hidden) position();
    };
    const close = (focus = false) => {
      if (typeof menu.hidePopover === 'function' && menu.matches(':popover-open')) menu.hidePopover();
      menu.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      search.setAttribute('aria-expanded', 'false');
      search.removeAttribute('aria-activedescendant');
      if (focus) trigger.focus({preventScroll: true});
    };
    const sync = () => {
      chips.replaceChildren();
      [...select.selectedOptions].forEach(option => {
        const chip = document.createElement('li');
        const name = document.createElement('span');
        name.textContent = option.text;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.textContent = '×';
        remove.disabled = select.disabled;
        remove.setAttribute('aria-label', labels.removeLabel + ': ' + option.text);
        remove.addEventListener('click', () => {
          option.selected = false;
          emit();
          trigger.focus({preventScroll: true});
        });
        chip.append(name, remove);
        chips.append(chip);
      });
      status.textContent = select.selectedOptions.length ? labels.selectedLabel + ': ' + select.selectedOptions.length : labels.noneLabel;
      if (!menu.hidden) build();
    };
    trigger.addEventListener('click', () => {
      if (!menu.hidden) { close(true); return; }
      search.value = '';
      build();
      menu.hidden = false;
      if (typeof menu.showPopover === 'function') menu.showPopover();
      trigger.setAttribute('aria-expanded', 'true');
      search.setAttribute('aria-expanded', 'true');
      position();
      search.focus({preventScroll: true});
    });
    search.addEventListener('input', build);
    search.addEventListener('keydown', event => {
      if (event.isComposing) return;
      if (event.key === 'Escape') { event.preventDefault(); close(true); }
      else if (event.key === 'Tab') { close(true); }
      else if (event.key === 'Enter') { event.preventDefault(); rows[active]?.click(); }
      else if (['ArrowDown', 'ArrowUp'].includes(event.key)) {
        event.preventDefault();
        if (rows.length) activate((active + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length, true);
      }
    });
    document.addEventListener('pointerdown', event => { if (!control.contains(event.target) && !menu.contains(event.target)) close(); });
    document.addEventListener('focusin', event => { if (!control.contains(event.target) && !menu.contains(event.target)) close(); });
    document.addEventListener('scroll', event => { if (!menu.hidden && !menu.contains(event.target)) position(); }, true);
    window.addEventListener('resize', () => { if (!menu.hidden) position(); });
    window.visualViewport?.addEventListener('resize', () => { if (!menu.hidden) position(); });
    select.addEventListener('change', sync);
    select.form?.addEventListener('reset', () => setTimeout(() => { close(); sync(); }, 0));
    sync();
  }
  const init = () => document.querySelectorAll('[data-gallery-control]').forEach(enhance);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
