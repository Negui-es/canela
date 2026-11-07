/* Shared form behavior: keep edits safe, explain errors and preserve native POSTs. */
document.addEventListener('DOMContentLoaded', () => {
  const t = text => typeof gettext === 'function' ? gettext(text) : text;
  const states = new Map();
  const snapshot = form => JSON.stringify([...new FormData(form)].map(([key, value]) =>
    [key, value instanceof File ? (value.name ? [value.name, value.size, value.lastModified] : '') : value]));
  const reveal = element => {
    if (!element) return;
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
  };
  const focusField = element => {
    if (!element) return;
    reveal(element);
    let target = element;
    if (element.matches('.select-native')) target = element.nextElementSibling?.querySelector('.select-trigger') || element;
    else if (element.matches('select[multiple]') && element.closest('[data-gallery-control]')) target = element.closest('[data-gallery-control]').querySelector('.gallery-add');
    else if (element.matches('[data-recipe-source]') && element.hidden) target = element.closest('[data-recipe-editor]').querySelector('[data-recipe-rows] input');
    else if (element.matches('input[type=file]')) target = element.closest('[data-uploader]')?.querySelector('[data-choose]') || element;
    else if (!element.matches('input,select,textarea,button')) target = element.querySelector('input:not([type=hidden]):not(:disabled),button,select,textarea') || element;
    if (!target.matches('input,select,textarea,button,a')) target.tabIndex = -1;
    target.focus({preventScroll: true});
    target.scrollIntoView({block: 'center', behavior: 'instant'});
  };
  document.querySelectorAll('[data-error-target]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    focusField(document.getElementById(link.dataset.errorTarget) || document.getElementById(link.dataset.errorTarget + '_error'));
  }));
  document.addEventListener('invalid', event => {
    reveal(event.target);
    if (event.target.form?.querySelector(':invalid') === event.target) queueMicrotask(() => focusField(event.target));
  }, true);
  const summary = document.querySelector('[data-form-errors]');
  if (summary) {
    summary.closest('form')?.querySelectorAll('[autofocus]').forEach(field => field.removeAttribute('autofocus'));
    summary.focus();
  }
  document.querySelectorAll('nav.space-navigation > a.active, .mobile-nav > a.active').forEach(link => link.setAttribute('aria-current', 'page'));
  document.querySelectorAll('input[type=password]').forEach(input => {
    const wrapper = document.createElement('div');
    wrapper.className = 'password-control';
    input.before(wrapper);
    wrapper.append(input);
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-toggle';
    toggle.textContent = t('Mostrar');
    toggle.setAttribute('aria-label', t('Mostrar contraseña'));
    toggle.setAttribute('aria-controls', input.id);
    toggle.setAttribute('aria-pressed', 'false');
    toggle.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      toggle.textContent = t(show ? 'Ocultar' : 'Mostrar');
      toggle.setAttribute('aria-label', t(show ? 'Ocultar contraseña' : 'Mostrar contraseña'));
      toggle.setAttribute('aria-pressed', String(show));
    });
    wrapper.append(toggle);
  });
  document.querySelectorAll('form[method=post]').forEach(form => {
    const state = {initial: snapshot(form), dirty: false, submitting: false, guarded: !form.querySelector('input[autocomplete=current-password],input[autocomplete=new-password],input[name=confirm_delete]')};
    states.set(form, state);
    const toolbar = form.querySelector('.editor-actions, .form-actions, .action-row');
    const status = document.createElement('span');
    status.className = 'form-save-status';
    status.setAttribute('role', 'status');
    status.hidden = true;
    toolbar?.prepend(status);
    const update = () => {
      const dirty = state.guarded && snapshot(form) !== state.initial;
      if (dirty !== state.dirty) {
        state.dirty = dirty;
        status.textContent = dirty ? t('Cambios sin guardar') : '';
        status.hidden = !dirty;
      }
    };
    form.addEventListener('input', update);
    form.addEventListener('change', update);
    form.addEventListener('canela:form-ready', () => { if (!state.dirty) state.initial = snapshot(form); });
  });
  document.addEventListener('submit', event => {
    const form = event.target, state = states.get(form);
    if (!state || event.defaultPrevented) return;
    if (state.submitting) { event.preventDefault(); return; }
    state.submitting = true;
    form.setAttribute('aria-busy', 'true');
    event.submitter?.setAttribute('aria-disabled', 'true');
  });
  window.addEventListener('beforeunload', event => {
    if ([...states.values()].some(state => state.dirty && !state.submitting)) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  window.addEventListener('pageshow', () => {
    states.forEach((state, form) => {
      state.submitting = false;
      form.removeAttribute('aria-busy');
      form.querySelectorAll('[aria-disabled=true]').forEach(button => button.removeAttribute('aria-disabled'));
    });
  });
});
