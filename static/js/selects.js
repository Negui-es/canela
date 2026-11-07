/* Native form values and events, with a shared, keyboard-accessible picker. */
(() => {
  'use strict';
  const instances = new Map();
  const suggestions = new Map();
  let sequence = 0;
  let opened = null;
  const t = text => typeof gettext === 'function' ? gettext(text) : text;
  const normalize = text => text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
  const optionText = option => /^-+$/.test(option.text.trim()) ? t('Selecciona una opción') : option.text;

  class Picker {
    constructor(select) {
      this.select = select;
      this.id = 'picker-' + (++sequence);
      this.labels = [...select.labels];
      this.label = this.labels.map(label => {
        const clone = label.cloneNode(true);
        clone.querySelectorAll('select,button,.custom-select,.help,.required').forEach(node => node.remove());
        return clone.textContent.trim();
      }).filter(Boolean).join(' ') || select.getAttribute('aria-label') || select.name;
      this.originalTabIndex = select.getAttribute('tabindex');
      this.originalAriaHidden = select.getAttribute('aria-hidden');
      this.originalLabelFor = this.labels.map(label => label.getAttribute('for'));
      this.wrapper = document.createElement('div');
      this.wrapper.className = 'custom-select';
      this.wrapper.picker = this;
      this.button = document.createElement('button');
      this.button.type = 'button';
      this.button.id = this.id;
      this.button.className = 'select-trigger';
      this.button.setAttribute('role', 'combobox');
      this.button.setAttribute('aria-haspopup', 'listbox');
      this.button.setAttribute('aria-expanded', 'false');
      this.button.setAttribute('aria-controls', this.id + '-list');
      this.button.setAttribute('aria-required', String(select.required));
      this.value = document.createElement('span');
      this.value.className = 'select-value';
      const arrow = document.createElement('span');
      arrow.className = 'select-chevron';
      arrow.setAttribute('aria-hidden', 'true');
      this.button.append(this.value, arrow);
      this.error = document.createElement('div');
      this.error.id = this.id + '-error';
      this.error.className = 'select-error';
      this.error.hidden = true;
      this.error.setAttribute('role', 'alert');
      this.wrapper.append(this.button, this.error);
      select.insertAdjacentElement('afterend', this.wrapper);
      select.classList.add('select-native');
      select.tabIndex = -1;
      select.setAttribute('aria-hidden', 'true');
      this.labels.forEach(label => { label.htmlFor = this.button.id; });

      this.menu = document.createElement('div');
      this.menu.className = 'select-menu';
      this.menu.hidden = true;
      this.menu.setAttribute('popover', 'manual');
      this.search = document.createElement('input');
      this.search.type = 'search';
      this.search.className = 'select-search';
      this.search.placeholder = t('Buscar opciones');
      this.search.setAttribute('aria-label', t('Buscar opciones'));
      this.search.setAttribute('role', 'combobox');
      this.search.setAttribute('aria-controls', this.id + '-list');
      this.search.setAttribute('aria-expanded', 'true');
      this.search.setAttribute('aria-autocomplete', 'list');
      this.search.autocomplete = 'off';
      this.list = document.createElement('div');
      this.list.id = this.id + '-list';
      this.list.className = 'select-options';
      this.list.setAttribute('role', 'listbox');
      this.list.setAttribute('aria-label', this.label);
      this.empty = document.createElement('p');
      this.empty.className = 'select-empty';
      this.empty.textContent = t('No hay opciones con ese nombre.');
      this.empty.setAttribute('role', 'status');
      this.menu.append(this.search, this.list, this.empty);
      document.body.append(this.menu);

      this.button.addEventListener('click', event => { event.preventDefault(); this.isOpen ? this.close() : this.open(); });
      this.button.addEventListener('keydown', event => this.keydown(event));
      this.search.addEventListener('keydown', event => this.keydown(event));
      this.search.addEventListener('input', () => this.filter());
      this.onChange = () => this.sync();
      this.onInvalid = event => {
        event.preventDefault();
        this.error.textContent = select.validationMessage;
        this.error.hidden = false;
        this.button.setAttribute('aria-invalid', 'true');
        this.button.setAttribute('aria-describedby', [select.getAttribute('aria-describedby'), this.error.id].filter(Boolean).join(' '));
        queueMicrotask(() => {
          if (select.form?.querySelector(':invalid') === select) { this.button.focus(); this.open(); }
        });
      };
      select.addEventListener('change', this.onChange);
      select.addEventListener('invalid', this.onInvalid);
      this.sync();
    }

    sync() {
      this.value.textContent = this.select.selectedOptions[0] ? optionText(this.select.selectedOptions[0]) : t('Selecciona una opción');
      this.button.setAttribute('aria-label', this.label + ': ' + this.value.textContent);
      if (this.button.disabled !== this.select.disabled) this.button.disabled = this.select.disabled;
      if (this.select.disabled) this.close(false);
      if (this.select.validity.valid) {
        this.error.hidden = true;
        if (this.select.getAttribute('aria-invalid') === 'true') this.button.setAttribute('aria-invalid', 'true');
        else this.button.removeAttribute('aria-invalid');
        const description = this.select.getAttribute('aria-describedby');
        if (description) this.button.setAttribute('aria-describedby', description);
        else this.button.removeAttribute('aria-describedby');
      }
    }

    open() {
      if (this.select.disabled || !this.button.getClientRects().length) return;
      opened?.close(false);
      opened = this;
      this.isOpen = true;
      this.search.value = '';
      this.search.hidden = this.select.options.length < 8;
      this.build();
      this.menu.hidden = false;
      if (typeof this.menu.showPopover === 'function') this.menu.showPopover();
      this.button.setAttribute('aria-expanded', 'true');
      this.position();
      if (!this.search.hidden) this.search.focus({preventScroll: true});
      this.setActive(this.rows.find(row => row.index === this.select.selectedIndex && !row.disabled) || this.enabled()[0]);
    }

    build() {
      this.list.replaceChildren();
      this.rows = [...this.select.options].filter(option => !option.hidden).map(option => {
        const element = document.createElement('div');
        element.id = this.id + '-option-' + option.index;
        element.className = 'select-option';
        element.setAttribute('role', 'option');
        element.setAttribute('aria-selected', String(option.selected));
        const disabled = option.disabled || (option.parentElement.tagName === 'OPTGROUP' && option.parentElement.disabled);
        element.setAttribute('aria-disabled', String(disabled));
        const text = document.createElement('span');
        text.textContent = optionText(option);
        const tick = document.createElement('span');
        tick.className = 'select-check';
        tick.setAttribute('aria-hidden', 'true');
        tick.textContent = '✓';
        element.append(text, tick);
        const row = {element, index: option.index, text: text.textContent, disabled};
        element.addEventListener('pointermove', () => { if (!disabled) this.setActive(row, false); });
        element.addEventListener('pointerdown', event => event.preventDefault());
        element.addEventListener('click', () => { if (!disabled) this.choose(row); });
        this.list.append(element);
        return row;
      });
      this.filter();
    }

    filter() {
      const query = normalize(this.search.value.trim());
      this.rows.forEach(row => { row.element.hidden = !normalize(row.text).includes(query); });
      this.empty.hidden = this.rows.some(row => !row.element.hidden);
      this.setActive(this.enabled()[0]);
      if (this.isOpen && !this.menu.hidden) this.position();
    }

    enabled() { return this.rows.filter(row => !row.disabled && !row.element.hidden); }

    setActive(row, scroll = true) {
      this.rows?.forEach(item => item.element.classList.toggle('is-active', item === row));
      this.active = row;
      [this.button, this.search].forEach(control => {
        if (row) control.setAttribute('aria-activedescendant', row.element.id);
        else control.removeAttribute('aria-activedescendant');
      });
      if (row && scroll && !this.menu.hidden) row.element.scrollIntoView({block: 'nearest'});
    }

    choose(row) {
      const changed = this.select.selectedIndex !== row.index;
      this.select.selectedIndex = row.index;
      this.sync();
      this.close();
      if (changed) {
        this.select.dispatchEvent(new Event('input', {bubbles: true}));
        this.select.dispatchEvent(new Event('change', {bubbles: true}));
      }
    }

    close(focus = true) {
      if (!this.isOpen) return;
      this.isOpen = false;
      this.prefix = '';
      clearTimeout(this.prefixTimer);
      if (typeof this.menu.hidePopover === 'function' && this.menu.matches(':popover-open')) this.menu.hidePopover();
      this.menu.hidden = true;
      this.button.setAttribute('aria-expanded', 'false');
      this.button.removeAttribute('aria-activedescendant');
      if (opened === this) opened = null;
      if (focus && this.button.isConnected && !this.button.disabled) this.button.focus({preventScroll: true});
    }

    keydown(event) {
      if (event.isComposing) return;
      if (event.key === 'Tab') { this.close(); return; }
      if (event.key === 'Escape') { event.preventDefault(); this.close(); return; }
      if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        if (!this.isOpen) {
          this.open();
          if (event.key === 'Home') this.setActive(this.enabled()[0]);
          if (event.key === 'End') this.setActive(this.enabled().at(-1));
          return;
        }
        const rows = this.enabled();
        const current = rows.indexOf(this.active);
        const index = event.key === 'Home' ? 0 : event.key === 'End' ? rows.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length;
        this.setActive(rows[index]);
      } else if (event.key === 'Enter' || (event.key === ' ' && event.target === this.button)) {
        event.preventDefault();
        if (!this.isOpen) this.open();
        else if (this.active) this.choose(this.active);
      } else if (event.target === this.button && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        if (!this.isOpen) this.open();
        if (!this.search.hidden) {
          this.search.value += event.key;
          this.filter();
        } else {
          this.prefix = (this.prefix || '') + event.key;
          clearTimeout(this.prefixTimer);
          this.prefixTimer = setTimeout(() => { this.prefix = ''; }, 800);
          this.setActive(this.enabled().find(row => normalize(row.text).startsWith(normalize(this.prefix))));
        }
      }
    }

    position() {
      const rect = this.button.getBoundingClientRect();
      const gap = 6;
      const gutter = 12;
      const viewport = window.visualViewport;
      const left = viewport?.offsetLeft || 0;
      const top = viewport?.offsetTop || 0;
      const viewportWidth = viewport?.width || window.innerWidth;
      const bottom = top + (viewport?.height || window.innerHeight);
      const width = Math.min(Math.max(rect.width, 240), viewportWidth - gutter * 2);
      const below = bottom - rect.bottom - gap - gutter;
      const above = rect.top - top - gap - gutter;
      const upwards = below < 190 && above > below;
      this.menu.style.width = width + 'px';
      this.menu.style.maxHeight = Math.max(90, Math.min(340, upwards ? above : below)) + 'px';
      const height = this.menu.getBoundingClientRect().height;
      this.menu.style.left = Math.max(left + gutter, Math.min(rect.left, left + viewportWidth - width - gutter)) + 'px';
      this.menu.style.top = Math.max(top + gutter, Math.min(upwards ? rect.top - gap - height : rect.bottom + gap, bottom - height - gutter)) + 'px';
    }

    destroy() {
      this.close(false);
      clearTimeout(this.prefixTimer);
      this.select.removeEventListener('change', this.onChange);
      this.select.removeEventListener('invalid', this.onInvalid);
      this.labels.forEach((label, index) => {
        if (this.originalLabelFor[index] === null) label.removeAttribute('for');
        else label.setAttribute('for', this.originalLabelFor[index]);
      });
      this.wrapper.remove();
      this.menu.remove();
      this.select.classList.remove('select-native');
      for (const [name, value] of [['tabindex', this.originalTabIndex], ['aria-hidden', this.originalAriaHidden]]) {
        if (value === null) this.select.removeAttribute(name);
        else this.select.setAttribute(name, value);
      }
      instances.delete(this.select);
    }
  }

  class Suggestions {
    constructor(input) {
      this.input = this.button = this.search = this.wrapper = input;
      this.listId = input.getAttribute('list');
      this.datalist = document.getElementById(this.listId);
      this.original = new Map(['list', 'role', 'aria-autocomplete', 'aria-controls', 'aria-expanded', 'autocomplete'].map(name => [name, input.getAttribute(name)]));
      this.label = [...input.labels].map(label => label.textContent.replace('*', '').trim()).join(' ') || input.name;
      this.id = 'picker-' + (++sequence);
      input.removeAttribute('list');
      input.classList.add('suggest-input');
      input.setAttribute('role', 'combobox');
      input.setAttribute('aria-autocomplete', 'list');
      input.setAttribute('aria-controls', this.id + '-list');
      input.setAttribute('aria-expanded', 'false');
      input.setAttribute('autocomplete', 'off');
      this.menu = document.createElement('div');
      this.menu.className = 'select-menu';
      this.menu.hidden = true;
      this.menu.setAttribute('popover', 'manual');
      this.list = document.createElement('div');
      this.list.id = this.id + '-list';
      this.list.className = 'select-options';
      this.list.setAttribute('role', 'listbox');
      this.list.setAttribute('aria-label', this.label);
      this.empty = document.createElement('p');
      this.empty.className = 'select-empty';
      this.empty.textContent = t('No hay opciones con ese nombre.');
      this.empty.setAttribute('role', 'status');
      this.menu.append(this.list, this.empty);
      document.body.append(this.menu);
      this.handlers = {
        focus: () => this.open(false),
        click: () => { if (!this.isOpen) this.open(false); },
        input: () => this.open(true),
        keydown: event => {
          if (event.isComposing) return;
          if (event.key === 'Escape' || event.key === 'Tab') { this.close(false); return; }
          if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (!this.isOpen) this.open(false);
            const rows = this.enabled();
            const index = rows.indexOf(this.active);
            this.setActive(rows[(index + (event.key === 'ArrowDown' ? 1 : -1) + rows.length) % rows.length]);
          } else if (event.key === 'Enter' && this.isOpen && this.active) {
            event.preventDefault();
            this.choose(this.active);
          }
        }
      };
      Object.entries(this.handlers).forEach(([name, handler]) => input.addEventListener(name, handler));
    }

    open(filter) {
      if (this.input.disabled || !this.input.getClientRects().length) return;
      if (opened !== this) opened?.close(false);
      opened = this;
      this.isOpen = true;
      this.list.replaceChildren();
      const query = filter ? normalize(this.input.value) : '';
      this.rows = [...this.datalist.options].filter(option => normalize(option.label + ' ' + option.value).includes(query)).map((option, index) => {
        const element = document.createElement('div');
        element.className = 'select-option';
        element.id = this.id + '-option-' + index;
        element.setAttribute('role', 'option');
        element.setAttribute('aria-selected', String(this.input.value === option.value));
        element.textContent = option.label || option.value;
        const row = {element, value: option.value, disabled: false};
        element.addEventListener('pointermove', () => this.setActive(row, false));
        element.addEventListener('pointerdown', event => event.preventDefault());
        element.addEventListener('click', () => this.choose(row));
        this.list.append(element);
        return row;
      });
      this.empty.hidden = this.rows.length > 0;
      this.menu.hidden = false;
      if (typeof this.menu.showPopover === 'function' && !this.menu.matches(':popover-open')) this.menu.showPopover();
      this.input.setAttribute('aria-expanded', 'true');
      this.position();
      this.setActive(this.rows.find(row => row.value === this.input.value));
    }

    enabled() { return this.rows; }
    setActive(row, scroll = true) { Picker.prototype.setActive.call(this, row, scroll); }
    position() { Picker.prototype.position.call(this); }
    choose(row) {
      this.input.value = row.value;
      this.input.dispatchEvent(new Event('input', {bubbles: true}));
      this.input.dispatchEvent(new Event('change', {bubbles: true}));
      this.close(false);
    }
    close() {
      if (!this.isOpen) return;
      this.isOpen = false;
      if (typeof this.menu.hidePopover === 'function' && this.menu.matches(':popover-open')) this.menu.hidePopover();
      this.menu.hidden = true;
      this.input.setAttribute('aria-expanded', 'false');
      this.input.removeAttribute('aria-activedescendant');
      if (opened === this) opened = null;
    }
    destroy() {
      this.close();
      Object.entries(this.handlers).forEach(([name, handler]) => this.input.removeEventListener(name, handler));
      this.menu.remove();
      this.input.classList.remove('suggest-input');
      for (const [name, value] of this.original) {
        if (value === null) this.input.removeAttribute(name);
        else this.input.setAttribute(name, value);
      }
      suggestions.delete(this.input);
    }
  }

  function enhance() {
    let restoreFocus = null;
    for (const [select, picker] of instances) if (!select.isConnected) {
      if (document.activeElement === picker.button) restoreFocus = select.id;
      picker.destroy();
    }
    document.querySelectorAll('select:not([multiple])').forEach(select => {
      if (select.size > 1 || instances.has(select)) return;
      instances.set(select, new Picker(select));
    });
    if (restoreFocus) instances.get(document.getElementById(restoreFocus))?.button.focus({preventScroll: true});
    for (const [input, picker] of suggestions) if (!input.isConnected) picker.destroy();
    document.querySelectorAll('input[list]').forEach(input => {
      if (!suggestions.has(input) && document.getElementById(input.getAttribute('list'))?.tagName === 'DATALIST') suggestions.set(input, new Suggestions(input));
    });
  }

  enhance();
  // HTMX restores response classes after an out-of-band swap. The new native
  // select may already be enhanced by then, so keep its managed hiding class.
  document.addEventListener('htmx:afterSettle', () => {
    instances.forEach((picker, select) => {
      if (select.isConnected) select.classList.add('select-native');
    });
  });
  new MutationObserver(records => {
    if (records.some(record => record.type === 'childList')) enhance();
    const changed = new Set();
    records.forEach(record => {
      const select = record.target instanceof Element ? record.target.closest('select') : null;
      if (select && instances.has(select)) changed.add(instances.get(select));
      if (suggestions.has(record.target) && record.target.disabled) suggestions.get(record.target).close();
    });
    changed.forEach(picker => { picker.sync(); if (picker.isOpen) picker.build(); });
  }).observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['disabled', 'selected']});
  document.addEventListener('pointerdown', event => { if (opened && !opened.wrapper.contains(event.target) && !opened.menu.contains(event.target)) opened.close(false); });
  document.addEventListener('focusin', event => { if (opened && !opened.wrapper.contains(event.target) && !opened.menu.contains(event.target)) opened.close(false); });
  document.addEventListener('scroll', event => { if (opened && !opened.menu.contains(event.target)) opened.close(false); }, true);
  window.addEventListener('resize', () => opened?.position());
  window.visualViewport?.addEventListener('resize', () => opened?.position());
  document.addEventListener('reset', event => setTimeout(() => {
    instances.forEach(picker => { if (picker.select.form === event.target) { picker.close(false); picker.sync(); } });
    suggestions.forEach(picker => { if (picker.input.form === event.target) picker.close(); });
  }, 0));
})();
