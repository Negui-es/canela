(() => {
  const menu = document.querySelector('#mobile-menu');
  const trigger = document.querySelector('[data-mobile-more]');
  if (!menu || !trigger) return;
  const mobile = window.matchMedia('(max-width: 850px)');
  trigger.addEventListener('click', () => {
    if (!mobile.matches || menu.open) return;
    menu.showModal();
    trigger.setAttribute('aria-expanded','true');
    document.body.classList.add('mobile-menu-open');
  });
  menu.querySelector('[data-mobile-menu-close]').addEventListener('click', () => menu.close());
  menu.addEventListener('click', event => {
    if (event.target !== menu) return;
    const rect = menu.getBoundingClientRect();
    if (event.clientY < rect.top || event.clientY > rect.bottom || event.clientX < rect.left || event.clientX > rect.right) menu.close();
  });
  menu.addEventListener('close', () => {
    trigger.setAttribute('aria-expanded','false');
    document.body.classList.remove('mobile-menu-open');
  });
  mobile.addEventListener('change', () => { if (!mobile.matches && menu.open) menu.close(); });
})();
