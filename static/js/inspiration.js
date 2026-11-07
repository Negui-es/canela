(() => {
  const feed = document.querySelector('[data-inspiration-feed]');
  if (!feed) return;
  const dialog = document.querySelector('[data-inspiration-dialog]');
  const content = dialog?.querySelector('[data-inspiration-dialog-content]');
  let trigger, previousOverflow, previousScrollX, previousScrollY, photos = [], photoIndex = 0;
  const showPhoto = index => {
    if (!photos.length) return;
    photoIndex = (index + photos.length) % photos.length;
    content.querySelector('[data-inspiration-image]').src = photos[photoIndex].dataset.inspirationPhoto;
    photos.forEach((button, i) => button.setAttribute('aria-pressed', String(i === photoIndex)));
    const position = content.querySelector('[data-inspiration-photo-position]');
    if (position) position.textContent = `${photoIndex + 1} / ${photos.length}`;
  };
  const openPresentation = summary => {
    if (!dialog?.showModal) return false;
    const detail = summary.closest('[data-inspiration-id]').querySelector('.inspiration-detail');
    content.replaceChildren(...[...detail.childNodes].map(node => node.cloneNode(true)));
    content.querySelector('[data-inspiration-title]').id = 'inspiration-dialog-title';
    photos = [...content.querySelectorAll('[data-inspiration-photo]')];
    trigger = summary;
    previousOverflow = document.documentElement.style.overflow;
    previousScrollX = window.scrollX;
    previousScrollY = window.scrollY;
    document.documentElement.style.overflow = 'hidden';
    dialog.showModal();
    dialog.scrollTop = 0;
    showPhoto(0);
    return true;
  };
  dialog?.addEventListener('click', event => {
    if (event.target === dialog || event.target.closest('[data-inspiration-close]')) dialog.close();
    const selected = event.target.closest('[data-inspiration-photo]');
    if (selected) showPhoto(photos.indexOf(selected));
    if (event.target.closest('[data-inspiration-prev]')) showPhoto(photoIndex - 1);
    if (event.target.closest('[data-inspiration-next-photo]')) showPhoto(photoIndex + 1);
  });
  dialog?.addEventListener('keydown', event => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      showPhoto(photoIndex + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  dialog?.addEventListener('close', () => {
    document.documentElement.style.overflow = previousOverflow;
    content.replaceChildren();
    photos = [];
    trigger?.focus({preventScroll: true});
    window.scrollTo({left: previousScrollX, top: previousScrollY, behavior: 'instant'});
  });
  let loading = false;
  const observer = 'IntersectionObserver' in window ? new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) load();
  }, {rootMargin: '500px'}) : null;
  const observe = () => {
    observer?.disconnect();
    const next = feed.querySelector('[data-inspiration-pagination]');
    if (next) observer?.observe(next);
  };
  async function load() {
    const pagination = feed.querySelector('[data-inspiration-pagination]');
    const link = pagination?.querySelector('a');
    if (!link || loading) return;
    loading = true;
    observer?.disconnect();
    feed.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(link.href, {headers: {'X-Inspiration-Batch': '1'}});
      if (!response.ok) throw new Error('load');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      // Cursor pagination avoids shifts when new pieces are published mid-scroll.
      for (const card of doc.querySelectorAll('[data-inspiration-id]')) {
        if (feed.querySelector(`[data-inspiration-id="${card.dataset.inspirationId}"]`)) card.remove();
      }
      pagination.remove();
      feed.append(...doc.body.childNodes);
      document.querySelector('[data-inspiration-error]').hidden = true;
      observe();
    } catch {
      document.querySelector('[data-inspiration-error]').hidden = false;
    } finally {
      loading = false;
      feed.removeAttribute('aria-busy');
    }
  }
  feed.addEventListener('click', event => {
    const summary = event.target.closest('.inspiration-piece > summary');
    if (summary && openPresentation(summary)) event.preventDefault();
    if (event.target.closest('[data-inspiration-next]')) {
      event.preventDefault();
      load();
    }
  });
  observe();
})();
