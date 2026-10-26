// Desktop version of the central button: the same three ways to register (Foto · Código · Voz), as a floating
// panel with the same spring animation. `cadenceRegisterMenu.open({ meal })` - meal is optional (desayuno, ...).
(function () {
  const MEALS = { desayuno: 'Desayuno', almuerzo: 'Almuerzo', merienda: 'Merienda', cena: 'Cena' };
  const ICONS = {
    foto: '<path d="M4 8a2 2 0 012-2h1.2l.9-1.5A2 2 0 0110 3.5h4a2 2 0 011.9 1l.9 1.5H18a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V8z" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="13" r="3.3" stroke="currentColor" stroke-width="1.7"/>',
    codigo: '<path d="M4 6v12M7.5 6v12M11 6v12M14 6v12M17 6v12M20 6v12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    voz: '<rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.7"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
  };
  let root = null;

  function hrefs(meal) {
    const m = meal ? `meal=${encodeURIComponent(meal)}` : '';
    return { foto: `scan.html${m ? `?${m}` : ''}`, codigo: `scan.html?mode=barcode${m ? `&${m}` : ''}`, voz: `voice.html${m ? `?${m}` : ''}` };
  }

  function close() { if (root) dismissOverlay(); }

  function open({ meal } = {}) {
    if (root) return;
    const h = hrefs(meal);
    const opt = (key, title, hint, primary, delay) => `
      <a class="rm-opt${primary ? ' primary' : ''}" href="${h[key]}" data-go style="--d:${delay}ms;">
        <span class="rm-ball"><svg width="30" height="30" viewBox="0 0 24 24" fill="none" aria-hidden="true">${ICONS[key]}</svg></span>
        <b class="disp">${title}</b><small>${hint}</small>
      </a>`;
    root = document.createElement('div');
    root.className = 'rm-scrim';
    root.innerHTML = `
      <div class="rm-card" role="dialog" aria-modal="true" aria-label="Registrar comida">
        <button type="button" class="rm-x" aria-label="Cerrar"><i data-ico="x"></i></button>
        <div class="rm-kick mono">REGISTRAR${meal && MEALS[meal] ? ` · ${MEALS[meal].toUpperCase()}` : ''}</div>
        <h2 class="disp">¿Cómo quieres añadirlo?</h2>
        <div class="rm-opts">
          ${opt('codigo', 'Código', 'Escanea un producto', false, 90)}
          ${opt('foto', 'Foto', 'La IA identifica tu plato', true, 0)}
          ${opt('voz', 'Voz', 'Dilo en voz alta', false, 150)}
        </div>
      </div>`;
    document.body.appendChild(root);
    requestAnimationFrame(() => requestAnimationFrame(() => root && root.classList.add('on')));
    if (window.sfx) sfx.play('open');
    pushOverlay(() => { const r = root; root = null; if (r) { r.classList.remove('on'); setTimeout(() => r.remove(), 260); } });
    root.addEventListener('click', (e) => { if (e.target === root) { if (window.sfx) sfx.play('close'); close(); } });
    root.querySelector('.rm-x').addEventListener('click', () => { if (window.sfx) sfx.play('close'); close(); });
    root.querySelectorAll('[data-go]').forEach((a) => a.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault();
      const href = a.getAttribute('href');
      if (window.sfx) sfx.play('tick');
      dismissOverlay(() => { window.location.href = href; });
    }));
    const first = root.querySelector('.rm-opt.primary');
    if (first) setTimeout(() => first.focus({ preventScroll: true }), 80);
  }

  window.cadenceRegisterMenu = { open };
})();
