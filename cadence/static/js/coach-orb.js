// The floating cadence orb (bottom right): opens the chat with cadence from any main screen.
// The chat itself (assistant.js) and the voice helpers load the first time the orb is touched.
(function () {
  const HIDE_ON = /\/(scan|confirm|voice|search|login|onboarding)\.html$/;
  if (HIDE_ON.test(location.pathname)) return;

  // A person in motion (Phosphor, duotone): someone who trains you.
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
    orb.innerHTML = `<span class="co-core">${cadenceIcons.icon('person-simple-run:duotone')}</span>`;
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
