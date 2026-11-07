(() => {
  'use strict';
  const script = document.currentScript;
  const sections = [...document.querySelectorAll('[data-install-app]')];
  const buttons = sections.flatMap(section => [...section.querySelectorAll('[data-install-button]')]);
  const standalone = window.matchMedia('(display-mode: standalone)');
  const installed = () => standalone.matches || window.navigator.standalone === true;
  const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent)
    || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  let installPrompt = null;

  const updateVisibility = () => sections.forEach(section => { section.hidden = installed(); });
  updateVisibility();
  standalone.addEventListener?.('change', updateVisibility);
  sections.forEach(section => {
    section.querySelector('[data-install-ios]').hidden = !isIOS;
    section.querySelector('[data-install-browser]').hidden = isIOS;
  });
  window.addEventListener('beforeinstallprompt', event => {
    if (!sections.length || installed()) return;
    event.preventDefault();
    installPrompt = event;
    buttons.forEach(button => { button.hidden = false; });
  });
  buttons.forEach(button => button.addEventListener('click', async () => {
    if (!installPrompt) return;
    const prompt = installPrompt;
    installPrompt = null;
    buttons.forEach(item => { item.hidden = true; });
    try { await prompt.prompt(); await prompt.userChoice; } catch { /* Manual instructions remain available. */ }
  }));
  window.addEventListener('appinstalled', () => {
    installPrompt = null;
    sections.forEach(section => { section.hidden = true; });
  });
  if ('serviceWorker' in navigator && window.isSecureContext && script?.dataset.serviceWorker) {
    const workerURL = script.dataset.serviceWorker;
    window.addEventListener('load', () => {
      navigator.serviceWorker.register(workerURL, {scope:'/', updateViaCache:'none'}).catch(() => {
        // Normal browsing still works when installation is unavailable.
      });
    }, {once:true});
  }
})();
