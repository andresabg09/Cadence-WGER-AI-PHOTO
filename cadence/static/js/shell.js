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
  const MARK = `<span class="scan-core"><svg width="22" height="22" viewBox="-16 -16 32 32" fill="none" aria-hidden="true"><defs><linearGradient id="sg-r" x1="-12" y1="12" x2="12" y2="-12" gradientUnits="userSpaceOnUse"><stop offset="0" style="stop-color: var(--accent-from)"/><stop offset="1" style="stop-color: var(--accent-to)"/></linearGradient><linearGradient id="sg-l" x1="-6" y1="-6" x2="6" y2="6" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#A592FF"/><stop offset="1" stop-color="#27B8E8"/></linearGradient></defs><g class="scan-ring"><circle r="11.5" stroke="rgba(255,255,255,0.12)" stroke-width="2.6"/><circle r="11.5" stroke="url(#sg-r)" stroke-width="2.6" stroke-linecap="round" stroke-dasharray="54 80" transform="rotate(-110)"/></g><circle r="6.2" fill="url(#sg-l)"/><circle r="3.5" fill="#0A0A12" fill-opacity="0.9"/><circle cx="-1.6" cy="-1.8" r="1.25" fill="#fff"/></svg></span>`;
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
      // Same idea as the phone's central button: the cadence mark, and it opens Foto · Código · Voz.
      return `<button type="button" class="scan" id="sideRegister" aria-haspopup="dialog">${MARK}<span>Registrar comida</span></button>`;
    }
    const active = item.key === current ? 'aria-current="page"' : '';
    const attrs = item.href ? `href="${item.href}"` : `href="#" data-soon="${item.label}"`;
    return `<a class="item" ${attrs} ${active}>${svg(item.key, 18)}${item.label}</a>`;
  }

  // The register panel is loaded the first time it is needed.
  function openRegisterMenu(options) {
    if (window.cadenceRegisterMenu) { window.cadenceRegisterMenu.open(options); return; }
    const tag = document.createElement('script');
    tag.src = 'static/js/register-menu.js';
    tag.onload = () => window.cadenceRegisterMenu.open(options);
    document.head.appendChild(tag);
  }
  window.openRegisterMenu = openRegisterMenu;

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
    const reg = document.getElementById('sideRegister');
    if (reg) reg.addEventListener('click', () => openRegisterMenu());
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
