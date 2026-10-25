// The floating cadence orb (bottom right): opens the chat with cadence from any main screen.
// The chat itself (assistant.js) and the voice helpers load the first time the orb is touched.
(function () {
  const HIDE_ON = /\/(scan|confirm|voice|search|login|onboarding)\.html$/;
  if (HIDE_ON.test(location.pathname)) return;

  // A personal trainer: cap, head, shoulders and a whistle on its cord.
  const MARK = `<svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true"><defs><linearGradient id="co-g" x1="6" y1="28" x2="26" y2="4" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#A592FF"/><stop offset="1" stop-color="#27B8E8"/></linearGradient></defs><path d="M5.5 29c0-5.6 4.5-9.2 10.5-9.2s10.5 3.6 10.5 9.2z" fill="url(#co-g)"/><circle cx="16" cy="13.4" r="4.6" fill="url(#co-g)"/><path d="M10.7 12.6a5.3 5.3 0 0 1 10.6 0z" fill="#fff"/><path d="M20.6 12.6h4.6a1.2 1.2 0 0 1 0 2.4h-4.6z" fill="#fff"/><path d="M12.6 20.6 16 25.2l3.4-4.6" stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" opacity=".85"/><rect x="14" y="24.4" width="4" height="3" rx="1.5" fill="#fff"/></svg>`;
  const SEEN = 'cadence_orb_seen';
  const SCRIPTS = ['static/js/recorder.js', 'static/js/dictation.js', 'static/js/assistant.js'];

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const tag = document.createElement('script');
      tag.src = src;
      tag.onload = resolve;
      tag.onerror = () => reject(new Error('No se pudo cargar el chat. Revisa tu conexión.'));
      document.head.appendChild(tag);
    });
  }

  async function openChat() {
    try {
      if (!window.cadenceAssistant) {
        for (const src of SCRIPTS) {
          const name = src.includes('recorder') ? 'cadenceRecorder' : src.includes('dictation') ? 'cadenceDictation' : 'cadenceAssistant';
          if (!window[name]) await loadScript(src);
        }
      }
      window.cadenceAssistant.open();
    } catch (err) {
      showToast(err.message);
    }
  }

  function build() {
    const orb = document.createElement('button');
    orb.type = 'button';
    orb.className = 'coach-orb';
    orb.setAttribute('aria-label', 'Hablar con tu entrenador cadence');
    orb.innerHTML = `<span class="co-core">${MARK}</span>`;
    document.body.appendChild(orb);

    let tip = null;
    const hideTip = () => { if (tip) { tip.remove(); tip = null; } };
    orb.addEventListener('click', () => {
      hideTip();
      try { localStorage.setItem(SEEN, '1'); } catch {}
      if (window.sfx) sfx.play('pick');
      openChat();
    });

    let seen = false;
    try { seen = localStorage.getItem(SEEN) === '1'; } catch {}
    if (!seen) {
      setTimeout(() => {
        tip = document.createElement('div');
        tip.className = 'coach-tip';
        tip.textContent = 'Pregúntame lo que quieras';
        document.body.appendChild(tip);
        setTimeout(hideTip, 7000);
      }, 1800);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
