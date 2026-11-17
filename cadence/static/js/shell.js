// Shared chrome (restructure of 17 nov 2026): ONE menu of five, the same on phone, tablet and computer.
//   Hoy · Recetas · (+) · Progreso · Perfil
// Phones and tablets get it as the bottom bar (with the cadence mark in the middle, which opens Foto · Código · Voz · Rápido);
// computers get it as the side bar. Progreso and Perfil are groups: their pages share tabs (Resumen | Historial | Retos |
// Premios and Yo | Objetivos | Ajustes) that switch with location.replace, so Back leaves the group instead of walking it.
// Nothing was removed: every page keeps its address; only the way to reach it changed.
// Pages opt in with <body class="with-shell" data-page="diario|ideas|progreso|historial|retos|premios|perfil|ajustes|...">.
(function () {
  const ICONS = {
    hoy: '<circle cx="12" cy="13" r="7.5" stroke="currentColor" stroke-width="1.8"/><path d="M12 9v4l2.5 2M9.5 3h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    recetas: '<path d="M4 11h16a8 8 0 01-16 0zM8 7c0-1.5 1-2 1-3M12 7c0-1.5 1-2 1-3M16 7c0-1.5 1-2 1-3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    progreso: '<path d="M5 19V9M12 19V5M19 19v-7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
    perfil: '<circle cx="12" cy="8" r="3.6" stroke="currentColor" stroke-width="1.8"/><path d="M5 20c1.4-3.8 4.2-5.6 7-5.6s5.6 1.8 7 5.6" stroke="currentColor" stroke-width="1.8"/>',
  };
  const MARK = `<span class="scan-core"><svg width="22" height="22" viewBox="-16 -16 32 32" fill="none" aria-hidden="true"><defs><linearGradient id="sg-r" x1="-12" y1="12" x2="12" y2="-12" gradientUnits="userSpaceOnUse"><stop offset="0" style="stop-color: var(--accent-from)"/><stop offset="1" style="stop-color: var(--accent-to)"/></linearGradient><linearGradient id="sg-l" x1="-6" y1="-6" x2="6" y2="6" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#A592FF"/><stop offset="1" stop-color="#27B8E8"/></linearGradient></defs><g class="scan-ring"><circle r="11.5" stroke="rgba(255,255,255,0.12)" stroke-width="2.6"/><circle r="11.5" stroke="url(#sg-r)" stroke-width="2.6" stroke-linecap="round" stroke-dasharray="54 80" transform="rotate(-110)"/></g><circle r="6.2" fill="url(#sg-l)"/><circle r="3.5" fill="#0A0A12" fill-opacity="0.9"/><circle cx="-1.6" cy="-1.8" r="1.25" fill="#fff"/></svg></span>`;
  const svg = (name, size) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" aria-hidden="true">${ICONS[name]}</svg>`;

  // The five destinations, in this order everywhere. `register` is the (+), not a page.
  const ITEMS = [
    { key: 'hoy', label: 'Hoy', href: 'index.html' },
    { key: 'recetas', label: 'Recetas', href: 'ideas.html' },
    { key: 'register', label: 'Registrar' },
    { key: 'progreso', label: 'Progreso', href: 'progress.html' },
    { key: 'perfil', label: 'Perfil', href: 'profile.html' },
  ];
  // Which of the five each page belongs to (data-page -> menu key).
  const OWNER = { diario: 'hoy', ideas: 'recetas', progreso: 'progreso', historial: 'progreso', retos: 'progreso', premios: 'progreso', perfil: 'perfil', ajustes: 'perfil' };
  // Pages that share tabs. Their files decide which tab is lit (goals.html says data-page="perfil" too).
  const GROUPS = {
    progreso: [['Resumen', 'progress.html'], ['Historial', 'history.html'], ['Retos', 'challenges.html'], ['Premios', 'awards.html']],
    perfil: [['Yo', 'profile.html'], ['Objetivos', 'goals.html'], ['Ajustes', 'settings.html']],
  };
  const NO_BAR = new Set(['escanear']); // full-screen camera, confirm and voice keep the whole screen
  const page = () => document.body.dataset.page || '';
  const owner = () => OWNER[page()] || '';
  const file = () => (location.pathname.split('/').pop() || 'index.html');

  // ---------------------------------------------------------------- register: (+) on phones, panel on computers
  function loadScript(src, ready) {
    const tag = document.createElement('script');
    tag.src = src;
    tag.onload = ready;
    document.head.appendChild(tag);
  }
  function openRegisterMenu(options) {
    if (window.cadenceRegisterMenu) { window.cadenceRegisterMenu.open(options); return; }
    loadScript('static/js/register-menu.js', () => window.cadenceRegisterMenu.open(options));
  }
  function openQuickLog(options) {
    if (window.cadenceQuickLog) { window.cadenceQuickLog.open(options || {}); return; }
    loadScript('static/js/quick-log.js', () => window.cadenceQuickLog.open(options || {}));
  }
  window.openRegisterMenu = openRegisterMenu;
  window.openQuickLog = openQuickLog;

  const LC_MEALS = { desayuno: 'Desayuno', almuerzo: 'Almuerzo', merienda: 'Merienda', cena: 'Cena' };
  let launcher = null;
  let scrim = null;
  let fab = null;
  let launcherMeal = null;

  const SAT_ICONS = {
    code: '<path d="M4 6v12M7.5 6v12M11 6v12M14 6v12M17 6v12M20 6v12" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
    foto: '<path d="M4 8a2 2 0 012-2h1.2l.9-1.5A2 2 0 0110 3.5h4a2 2 0 011.9 1l.9 1.5H18a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V8z" stroke="currentColor" stroke-width="1.7"/><circle cx="12" cy="13" r="3.3" stroke="currentColor" stroke-width="1.7"/>',
    voz: '<rect x="9" y="3" width="6" height="11" rx="3" stroke="currentColor" stroke-width="1.7"/><path d="M5.5 11a6.5 6.5 0 0013 0M12 17.5V21" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    rapido: '<path d="M13 3L5 14h6l-1 7 8-11h-6l1-7z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>',
    etiqueta: '<rect x="5" y="3" width="14" height="18" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  };
  const ball = (name, size) => `<span class="lc-ball"><svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" aria-hidden="true">${SAT_ICONS[name]}</svg></span>`;

  function launcherHtml() {
    return `
      <div class="launcher" id="launcher">
        <div class="lc-halo"></div>
        <span class="lc-meal mono" id="lcMeal"></span>
        <a class="lc-pill" href="scan.html?mode=label" data-launch tabindex="-1">${SAT_ICONS.etiqueta ? `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">${SAT_ICONS.etiqueta}</svg>` : ''}Leer la etiqueta de un producto</a>
        <svg class="lc-arc" width="320" height="230" viewBox="-160 -210 320 230" fill="none" aria-hidden="true">
          <defs><linearGradient id="lcg-a" x1="-120" y1="0" x2="120" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" style="stop-color: var(--accent-from); stop-opacity: 0"/><stop offset="0.5" style="stop-color: var(--accent-to)"/><stop offset="1" style="stop-color: var(--accent-from); stop-opacity: 0"/></linearGradient></defs>
          <path d="M -117 -67 Q 0 -205 117 -67" pathLength="100" stroke="url(#lcg-a)" stroke-width="1.4" stroke-linecap="round"/>
        </svg>
        <a class="lc-sat lc-code" href="scan.html?mode=barcode" data-launch aria-label="Código: escanea un producto" tabindex="-1">${ball('code', 24)}<span class="lc-label mono">CÓDIGO</span></a>
        <a class="lc-sat lc-foto" href="scan.html" data-launch aria-label="Foto: la IA identifica tu plato" tabindex="-1">${ball('foto', 30)}<span class="lc-label mono">FOTO</span></a>
        <a class="lc-sat lc-voz" href="voice.html" data-launch aria-label="Voz: dilo en voz alta" tabindex="-1">${ball('voz', 24)}<span class="lc-label mono">VOZ</span></a>
        <a class="lc-sat lc-quick" href="#rapido" data-quick aria-label="Rápido: solo calorías o un básico con medidas de casa" tabindex="-1">${ball('rapido', 24)}<span class="lc-label mono">RÁPIDO</span></a>
        <button type="button" class="lc-fab" id="fabBtn" aria-expanded="false" aria-haspopup="true" aria-label="Registrar comida: foto, código, voz o rápido">
          <span class="lc-core"><svg width="33" height="33" viewBox="-16 -16 32 32" fill="none" aria-hidden="true">
            <defs><linearGradient id="lcg-r" x1="-12" y1="12" x2="12" y2="-12" gradientUnits="userSpaceOnUse"><stop offset="0" style="stop-color: var(--accent-from)"/><stop offset="1" style="stop-color: var(--accent-to)"/></linearGradient>
            <linearGradient id="lcg-l" x1="-6" y1="-6" x2="6" y2="6" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#A592FF"/><stop offset="1" stop-color="#27B8E8"/></linearGradient></defs>
            <g class="lc-ring"><circle r="11.5" stroke="rgba(255,255,255,0.10)" stroke-width="2.6"/><circle r="11.5" stroke="url(#lcg-r)" stroke-width="2.6" stroke-linecap="round" stroke-dasharray="54 80" transform="rotate(-110)"/></g>
            <circle r="6.2" fill="url(#lcg-l)"/><circle r="3.5" fill="#0A0A12" fill-opacity="0.9"/><circle cx="-1.6" cy="-1.8" r="1.25" fill="#fff"/>
            <path d="M9.6 -12.4l.7 2.1 2.1.7-2.1.7-.7 2.1-.7-2.1-2.1-.7 2.1-.7z" fill="#fff"/></svg></span>
        </button>
      </div>`;
  }

  function setLauncher(open) {
    if (!launcher) return;
    launcher.classList.toggle('open', open);
    scrim.classList.toggle('open', open);
    fab.setAttribute('aria-expanded', String(open));
    launcher.querySelectorAll('.lc-sat, .lc-pill').forEach((a) => a.setAttribute('tabindex', open ? '0' : '-1'));
  }
  // Which meal the options register into (null = the one the photo's time suggests).
  function setLauncherMeal(meal) {
    if (!launcher) return;
    launcherMeal = meal && LC_MEALS[meal] ? meal : null;
    const q = launcherMeal ? `meal=${encodeURIComponent(launcherMeal)}` : '';
    launcher.querySelector('.lc-foto').setAttribute('href', `scan.html${q ? `?${q}` : ''}`);
    launcher.querySelector('.lc-code').setAttribute('href', `scan.html?mode=barcode${q ? `&${q}` : ''}`);
    launcher.querySelector('.lc-voz').setAttribute('href', `voice.html${q ? `?${q}` : ''}`);
    launcher.querySelector('.lc-pill').setAttribute('href', `scan.html?mode=label${q ? `&${q}` : ''}`);
    const chip = launcher.querySelector('#lcMeal');
    chip.textContent = launcherMeal ? `AGREGAR ${LC_MEALS[launcherMeal].toUpperCase()}` : '';
    chip.classList.toggle('has', !!launcherMeal);
  }
  function openLauncher(meal) {
    if (!launcher) { openRegisterMenu({ meal }); return; }
    setLauncherMeal(meal || null);
    if (launcher.classList.contains('open')) return;
    setLauncher(true);
    if (window.sfx) sfx.play('open');
    pushOverlay(() => setLauncher(false)); // the system Back button closes it and stays on the same page
  }
  function closeLauncher(quiet) {
    if (!launcher || !launcher.classList.contains('open')) return;
    if (!quiet && window.sfx) sfx.play('close');
    dismissOverlay();
  }
  // From "Agregar almuerzo" and similar: phones and tablets open the central menu; computers open the register panel.
  function openRegister(meal) {
    if (!launcher || window.matchMedia('(min-width: 1024px)').matches) { openRegisterMenu({ meal }); return; }
    openLauncher(meal);
  }
  window.openRegister = openRegister;
  window.openLauncher = openLauncher;
  window.closeLauncher = closeLauncher;

  function wireLauncher() {
    launcher = document.getElementById('launcher');
    scrim = document.getElementById('lcScrim');
    fab = document.getElementById('fabBtn');
    fab.addEventListener('click', () => (launcher.classList.contains('open') ? closeLauncher() : openLauncher()));
    scrim.addEventListener('click', () => closeLauncher());
    launcher.querySelectorAll('[data-launch]').forEach((a) => a.addEventListener('click', (e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey) return;
      e.preventDefault();
      const href = a.getAttribute('href');
      if (window.sfx) sfx.play('tick');
      dismissOverlay(() => { window.location.href = href; }); // close first, so Back from the camera lands on a clean page
    }));
    launcher.querySelector('[data-quick]').addEventListener('click', (e) => {
      e.preventDefault();
      const meal = launcherMeal;
      if (window.sfx) sfx.play('tick');
      dismissOverlay(() => openQuickLog({ meal }));
    });
  }

  // ---------------------------------------------------------------- bottom bar (phones and tablets)
  function buildBottomBar() {
    if (NO_BAR.has(page()) || document.querySelector('.tab-bar')) return;
    const current = owner();
    const tab = (item) => {
      const on = item.key === current;
      const dot = item.key === 'progreso' ? '<i class="tab-dot" id="retosDot" hidden></i>' : '';
      return `<a class="tab${on ? ' active' : ''}" href="${item.href}" ${on ? 'aria-current="page"' : ''} data-tab="${item.key}"><span class="tab-ico">${svg(item.key, 20)}${dot}</span><span>${item.label}</span></a>`;
    };
    const bar = document.createElement('nav');
    bar.className = 'tab-bar';
    bar.setAttribute('aria-label', 'Principal');
    bar.innerHTML = ITEMS.map((item) => (item.key === 'register' ? launcherHtml() : tab(item))).join('');
    const sc = document.createElement('div');
    sc.className = 'lc-scrim';
    sc.id = 'lcScrim';
    document.body.append(sc, bar);
    document.body.classList.add('has-tabbar');
    wireLauncher();
  }

  // ---------------------------------------------------------------- side bar (computers)
  function buildSidebar() {
    const current = owner();
    const item = (it) => {
      if (it.key === 'register') {
        return `<button type="button" class="scan" id="sideRegister" aria-haspopup="dialog">${MARK}<span>Registrar</span></button>`;
      }
      const on = it.key === current;
      const dot = it.key === 'progreso' ? '<i class="side-dot" id="sideRetosDot" hidden></i>' : '';
      return `<a class="item" href="${it.href}" ${on ? 'aria-current="page"' : ''}>${svg(it.key, 18)}${it.label}${dot}</a>`;
    };
    const nav = document.createElement('nav');
    nav.className = 'side-nav';
    nav.setAttribute('aria-label', 'Principal');
    nav.innerHTML = `
      <div class="brand"><img src="static/icons/icon-192.png" alt=""><span>cadence</span></div>
      ${ITEMS.map(item).join('')}
      <div class="grow"></div>
      <div class="conn" id="wgerConn"><span class="dot"></span><span id="wgerConnText">Comprobando conexión…</span></div>
    `;
    document.body.insertBefore(nav, document.body.firstChild);
    nav.querySelector('#sideRegister').addEventListener('click', () => openRegisterMenu());
  }

  // ---------------------------------------------------------------- group tabs (Progreso, Perfil)
  function buildGroupTabs() {
    const tabs = GROUPS[owner()];
    if (!tabs) return;
    const here = file();
    if (!tabs.some(([, href]) => href === here)) return; // a detail page (Recordatorios) keeps only its back arrow
    const head = document.querySelector('.page-head');
    if (!head) return;
    const row = document.createElement('div');
    row.className = 'group-tabs';
    row.setAttribute('role', 'tablist');
    row.style.setProperty('--n', tabs.length);
    row.innerHTML = tabs.map(([label, href]) => {
      const on = href === here;
      return `<a class="gt${on ? ' on' : ''}" role="tab" aria-selected="${on}" href="${href}" data-replace${on ? ' aria-current="page"' : ''}>${label}${href === 'challenges.html' ? '<i class="gt-dot" id="groupRetosDot" hidden></i>' : ''}</a>`;
    }).join('');
    head.insertAdjacentElement('afterend', row);
    row.addEventListener('click', (e) => {
      const a = e.target.closest('a.gt');
      if (a && a.classList.contains('on')) e.preventDefault();
      else if (a && window.sfx) sfx.play('pick');
    });
  }

  // A small dot on Progreso (and on the Retos tab) when there are coins or a gift to collect.
  async function paintClaimDot() {
    if (!document.getElementById('retosDot') && !document.getElementById('sideRetosDot')) return;
    try {
      const data = await apiGet('api/challenges/dot');
      ['retosDot', 'sideRetosDot', 'groupRetosDot'].forEach((id) => { const el = document.getElementById(id); if (el) el.hidden = !data.claimable; });
    } catch { /* the dot is a nicety */ }
  }
  window.cadencePaintClaimDot = paintClaimDot;

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

  // Anything marked data-register opens the register menu, on every page (data-register="almuerzo" picks the meal).
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-register]');
    if (!b) return;
    e.preventDefault();
    openRegister(b.getAttribute('data-register') || null);
  });

  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.classList.contains('with-shell')) {
      buildSidebar();
      buildBottomBar();
      buildGroupTabs();
      refreshConnection();
      paintClaimDot();
      const orb = document.createElement('script');
      orb.src = 'static/js/coach-orb.js';
      document.head.appendChild(orb);
    }
    watchConnectivity();
  });
})();
