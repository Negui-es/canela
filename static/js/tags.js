document.querySelectorAll('[data-tag-input]').forEach(input => {
  const normalize = value => value.normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const buttons = [...input.closest('form').querySelectorAll('[data-add-tag]')];
  const update = () => {
    const selected = input.value.split(/[,;\n]/).map(normalize).filter(Boolean);
    buttons.forEach(button => button.setAttribute('aria-pressed', String(selected.includes(normalize(button.dataset.addTag)))));
  };
  buttons.forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      const tags = input.value.split(/[,;\n]/).map(normalize).filter(Boolean);
      const name = button.dataset.addTag;
      const position = tags.indexOf(name);
      if (position < 0) tags.push(name);
      else tags.splice(position, 1);
      input.value = tags.join(', ');
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    });
  });
  input.addEventListener('input', update);
  update();
});
