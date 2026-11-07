document.querySelectorAll('.search-toolbar').forEach(form => {
  const filters = form.querySelector('[data-search-filters]');
  const indicator = form.querySelector('[data-active-filters]');
  const reset = form.querySelector('[data-search-reset]');
  const mobile = window.matchMedia('(max-width: 850px)');
  const updateLayout = () => { filters.open = !mobile.matches; };
  const updateIndicator = () => {
    const active = [...form.querySelectorAll('select')].filter(select =>
      select.name === 'scope' ? select.value === 'shared' : Boolean(select.value));
    indicator.hidden = !active.length;
    indicator.querySelector('[data-active-filter-number]').textContent = String(active.length);
    reset.hidden = indicator.hidden && !form.querySelector('input[name=q]').value;
  };
  updateLayout();
  updateIndicator();
  mobile.addEventListener('change', updateLayout);
  form.addEventListener('change', updateIndicator);
  form.addEventListener('input', updateIndicator);
});
document.addEventListener('htmx:afterSwap', event => {
  if (!['piece-results', 'resource-results'].includes(event.detail.target?.id)) return;
  const feedback = document.querySelector('[data-search-feedback]');
  if (!feedback) return;
  feedback.classList.remove('is-error');
  feedback.hidden = false;
  const results = document.getElementById(event.detail.target.id);
  feedback.textContent = gettext('Resultados') + ': ' + results.querySelector('.result-count strong')?.textContent;
});
const showSearchError = event => {
  const form = event.detail.elt?.closest('.search-toolbar');
  if (!form) return;
  const feedback = form.querySelector('[data-search-feedback]');
  feedback.classList.add('is-error');
  feedback.hidden = false;
  feedback.textContent = gettext('No se pudo actualizar la búsqueda. Vuelve a intentarlo.');
};
document.addEventListener('htmx:responseError', showSearchError);
document.addEventListener('htmx:sendError', showSearchError);
