// The floating cadence orb (bottom right): opens the chat with cadence from any main screen.
// The chat itself (assistant.js) and the voice helpers load the first time the orb is touched.
(function () {
  const HIDE_ON = /\/(scan|confirm|voice|search|login|onboarding)\.html$/;
  if (HIDE_ON.test(location.pathname)) return;

  const MARK = `<svg width="26" height="26" viewBox="-16 -16 32 32" fill="none" aria-hidden="true"><defs><linearGradient id="co-r" x1="-12" y1="12" x2="12" y2="-12" gradientUnits="userSpaceOnUse"><stop offset="0" style="stop-color: var(--accent-from)"/><stop offset="1" style="stop-color: var(--accent-to)"/></linearGradient><linearGradient id="co-l" x1="-6" y1="-6" x2="6" y2="6" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#A592FF"/><stop offset="1" stop-color="#27B8E8"/></linearGradient></defs><circle r="11.5" stroke="rgba(255,255,255,0.12)" stroke-width="2.6"/><circle r="11.5" stroke="url(#co-r)" stroke-width="2.6" stroke-linecap="round" stroke-dasharray="54 80" transform="rotate(-110)"/><circle r="6.2" fill="url(#co-l)"/><circle r="3.5" fill="#0A0A12" fill-opacity="0.9"/><circle cx="-1.6" cy="-1.8" r="1.25" fill="#fff"/></svg>`;
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
    orb.setAttribute('aria-label', 'Hablar con cadence');
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
