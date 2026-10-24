// "Instalar app" sheet (mockup: Instalar app). Shown on the second visit or
// later, never when already installed, and not again for 14 days after "Ahora no".
(function () {
  const VISITS_KEY = 'cadence_visits';
  const DISMISSED_KEY = 'cadence_install_dismissed';
  let deferredPrompt = null;

  const standalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
  const isIos = () => /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
  const get = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
  const set = (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };

  function eligible() {
    if (standalone()) return false;
    const dismissed = Number(get(DISMISSED_KEY) || 0);
    if (dismissed && Date.now() - dismissed < 14 * 86400000) return false;
    return Number(get(VISITS_KEY) || 0) >= 2;
  }

  function close() {
    document.querySelectorAll('.install-scrim, .install-sheet').forEach((el) => el.remove());
  }

  function show() {
    if (document.querySelector('.install-sheet') || !eligible()) return;
    if (!deferredPrompt && !isIos()) return;

    const scrim = document.createElement('div');
    scrim.className = 'install-scrim';
    const sheet = document.createElement('div');
    sheet.className = 'install-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Instalar cadence');
    sheet.innerHTML = `
      <div class="grab"></div>
      <img class="app-icon" src="static/icons/icon-192.png" alt="">
      <div style="text-align:center;margin-bottom:20px;">
        <h2 class="disp" style="margin:0 0 8px;font-size:19px;font-weight:700;">Instala cadence</h2>
        <p style="margin:0;font-size:13px;color:var(--ink-soft);line-height:1.5;padding:0 10px;">Añádela a tu pantalla de inicio: carga al instante, pantalla completa sin barra del navegador, y acceso directo a la cámara desde el ícono.</p>
      </div>
      ${deferredPrompt ? '<button class="btn-primary" id="installNow">Instalar ahora</button>' : ''}
      <button id="installLater" style="display:block;width:100%;min-height:44px;margin-top:10px;background:none;border:none;color:var(--ink-soft);font-size:12.5px;font-weight:600;cursor:pointer;">Ahora no</button>
      ${isIos() && !deferredPrompt ? '<div style="margin-top:12px;background:rgba(127,127,140,0.08);border:1px solid var(--card-border);border-radius:14px;padding:11px 13px;font-size:11.5px;color:var(--ink-soft);line-height:1.45;"><strong style="color:var(--ink);">¿En iPhone?</strong> Toca Compartir y luego "Añadir a pantalla de inicio".</div>' : ''}
    `;
    document.body.append(scrim, sheet);
    pushOverlay(close);

    const later = () => { set(DISMISSED_KEY, String(Date.now())); dismissOverlay(); };
    scrim.addEventListener('click', later);
    sheet.querySelector('#installLater').addEventListener('click', later);
    const now = sheet.querySelector('#installNow');
    if (now) {
      now.addEventListener('click', async () => {
        deferredPrompt.prompt();
        await deferredPrompt.userChoice.catch(() => {});
        deferredPrompt = null;
        dismissOverlay();
      });
    }
  }

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    show();
  });
  window.addEventListener('appinstalled', () => { deferredPrompt = null; dismissOverlay(); });

  document.addEventListener('DOMContentLoaded', () => {
    set(VISITS_KEY, String(Number(get(VISITS_KEY) || 0) + 1));
    setTimeout(show, 1500);
  });
})();
