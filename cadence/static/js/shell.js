// Shared chrome: desktop sidebar, connection dot, offline banner.
// Pages opt in with <body class="with-shell" data-page="diario|escanear|...">.
(function () {
  const ICONS = {
    diario: '<rect x="4" y="4" width="16" height="16" rx="5" stroke="currentColor" stroke-width="1.8"/><path d="M8 10h8M8 14h5" stroke="currentColor" stroke-width="1.8"/>',
    camara: '<path d="M4 8a2 2 0 012-2h1.2l.9-1.5A2 2 0 0110 3.5h4a2 2 0 011.9 1l.9 1.5H18a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V8z" stroke="currentColor" stroke-width="1.8"/><circle cx="12" cy="13" r="3.4" stroke="currentColor" stroke-width="1.8"/>',
    progreso: '<path d="M5 19V9M12 19V5M19 19v-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    historial: '<circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.8"/><path d="M12 8v4l3 2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    perfil: '<circle cx="12" cy="8" r="3.6" stroke="currentColor" stroke-width="1.8"/><path d="M5 20c1.4-3.8 4.2-5.6 7-5.6s5.6 1.8 7 5.6" stroke="currentColor" stroke-width="1.8"/>',
    ajustes: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="15" cy="7" r="2" stroke="currentColor" stroke-width="1.8"/><circle cx="9" cy="17" r="2" stroke="currentColor" stroke-width="1.8"/>',
  };
  const svg = (name, size) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" aria-hidden="true">${ICONS[name]}</svg>`;

  // href null = screen from a later block ("próximamente").
  const ITEMS = [
    { key: 'diario', label: 'Diario', href: 'index.html' },
    { key: 'scan', label: 'Escanear con IA', href: 'scan.html' },
    { key: 'progreso', label: 'Progreso', href: 'progress.html' },
    { key: 'historial', label: 'Historial', href: 'history.html' },
  ];
  const BOTTOM = [
    { key: 'perfil', label: 'Perfil', href: 'profile.html' },
    { key: 'ajustes', label: 'Ajustes', href: 'settings.html' },
  ];

  function itemHtml(item, current) {
    if (item.key === 'scan') {
      return `<a class="scan" href="${item.href}" ${current === 'escanear' ? 'aria-current="page"' : ''}>${svg('camara', 19)} ${item.label}</a>`;
    }
    const active = item.key === current ? 'aria-current="page"' : '';
    const attrs = item.href ? `href="${item.href}"` : `href="#" data-soon="${item.label}"`;
    return `<a class="item" ${attrs} ${active}>${svg(item.key, 18)}${item.label}</a>`;
  }

  function buildSidebar() {
    const current = document.body.dataset.page || '';
    const nav = document.createElement('nav');
    nav.className = 'side-nav';
    nav.setAttribute('aria-label', 'Principal');
    nav.innerHTML = `
      <div class="brand"><img src="static/icons/icon-192.png" alt=""><span>cadence</span></div>
      ${ITEMS.map((i) => itemHtml(i, current)).join('')}
      <div class="grow"></div>
      ${BOTTOM.map((i) => itemHtml(i, current)).join('')}
      <div class="conn" id="wgerConn"><span class="dot"></span><span id="wgerConnText">Comprobando conexión…</span></div>
    `;
    nav.addEventListener('click', (e) => {
      const soon = e.target.closest('[data-soon]');
      if (soon) {
        e.preventDefault();
        showToast(`${soon.dataset.soon}: próximamente`, 'warn');
      }
    });
    document.body.insertBefore(nav, document.body.firstChild);
  }

  async function refreshConnection() {
    const box = document.getElementById('wgerConn');
    const text = document.getElementById('wgerConnText');
    if (!box) return;
    try {
      const status = await apiGet('api/wger-status');
      box.className = `conn ${status.ok ? 'ok' : 'bad'}`;
      text.textContent = status.ok ? 'Conectado' : 'Sin conexión con el servidor';
    } catch {
      box.className = 'conn bad';
      text.textContent = 'Sin conexión';
    }
  }

  function watchConnectivity() {
    const show = () => showBanner('offline', 'Sin conexión. Tus registros se guardan y se sincronizan solos al volver.');
    const back = async () => {
      hideBanner('offline');
      try {
        const sent = await flushPending();
        if (sent) showToast(`${sent} registro${sent === 1 ? '' : 's'} sincronizado${sent === 1 ? '' : 's'}`, 'warn');
        if (sent && typeof loadToday === 'function') loadToday();
      } catch (err) {
        showToast(`No se pudo sincronizar: ${err.message}`);
      }
    };
    window.addEventListener('offline', show);
    window.addEventListener('online', back);
    if (!navigator.onLine) show();
    else if (readPending().length) back();
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.classList.contains('with-shell')) {
      buildSidebar();
      refreshConnection();
    }
    watchConnectivity();
  });
})();
