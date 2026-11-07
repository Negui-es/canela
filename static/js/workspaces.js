document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-workshop-picker]').forEach(form => {
    const select = form.querySelector('[data-workshop-select]');
    const open = () => { if (select.value) window.location.assign(select.value); };
    select.addEventListener('change', open);
    form.querySelector('[data-workshop-go]').addEventListener('click', open);
  });
});
