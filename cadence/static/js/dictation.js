// Dictation: the voice becomes TEXT in the message box (like Claude does), the person reads it, fixes it and sends it themself.
// Tapping the microphone again stops listening; nothing is ever sent by voice on its own.
//
// It does NOT trust the browser to transcribe: every time it records the audio as a safety net AND, where the browser has it, asks
// the browser's speech recognition to write live. When the person stops:
//   - if the live recognition wrote something, that text is what they see (the recording is dropped);
//   - if it wrote nothing (Opera, Brave and other Chromium builds expose it but have no service behind it; the iPhone app has none),
//     the recording goes to Gemini and its text lands in the same box.
// A level meter around the button shows that the microphone really hears them.
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANG = (() => { const l = navigator.language || ''; return l.toLowerCase().startsWith('es') ? l : 'es-PA'; })();
  const FLAG = 'cadence_live_dictation_broken';
  const liveBroken = () => { try { return localStorage.getItem(FLAG) === '1'; } catch { return false; } };
  const markBroken = () => { try { localStorage.setItem(FLAG, '1'); } catch { /* no storage */ } };

  function grow(field) {
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 140)}px`;
    // It just grows; only a very long text scrolls inside it (and without a visible bar).
    field.style.overflowY = field.scrollHeight > 140 ? 'auto' : 'hidden';
  }

  // Watches the microphone level; calls onLevel(0..1) every frame. Returns { stop(), peak() }.
  function meter(stream, onLevel) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx || !stream) return { stop() {}, peak: () => 1 };
    let ctx; let raf; let peak = 0;
    try {
      ctx = new Ctx();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 512;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let sum = 0;
        for (let i = 0; i < data.length; i += 1) { const x = (data[i] - 128) / 128; sum += x * x; }
        const rms = Math.sqrt(sum / data.length);
        peak = Math.max(peak, rms);
        onLevel(Math.min(1, rms * 6));
        raf = requestAnimationFrame(tick);
      };
      tick();
    } catch { return { stop() {}, peak: () => 1 }; }
    return { stop() { cancelAnimationFrame(raf); try { ctx.close(); } catch { /* closed */ } onLevel(0); }, peak: () => peak };
  }

  // field: the textarea; button: the microphone button; onHint(text): a short line telling what is happening; onError(text).
  function attach({ field, button, onHint, onError }) {
    let mode = 'idle';       // idle | on | working
    let rec = null;          // live recognition (the current instance only)
    let recorder = null;     // the safety-net recording
    let level = null;
    let liveWrote = false;
    let base = '';
    let restarts = [];
    let startedAt = 0;
    let clock = null;
    let usedLive = false;

    const hint = (t) => { if (onHint) onHint(t); };
    const fail = (t) => { if (onError) onError(t); else hint(t); };
    const put = (text) => {
      field.value = text;
      grow(field);
      field.dispatchEvent(new Event('input', { bubbles: true }));
    };
    const spaced = () => (field.value && !/\s$/.test(field.value) ? `${field.value} ` : field.value);
    const ui = (on, busy) => {
      button.classList.toggle('rec', on);
      button.setAttribute('aria-pressed', String(on));
      button.disabled = Boolean(busy);
    };

    // ---------------------------------------------------------------- live recognition (an extra, never the only way)
    function dropLive() {
      if (!rec) return;
      const old = rec; rec = null;
      old.onresult = old.onerror = old.onend = null;
      try { old.stop(); } catch { /* already stopped */ }
    }
    function startLive() {
      const mine = new SR();
      rec = mine;
      mine.lang = LANG;
      mine.continuous = true;
      mine.interimResults = true;
      mine.onresult = (e) => {
        if (rec !== mine) return;
        let said = '';
        for (let i = 0; i < e.results.length; i += 1) said += e.results[i][0].transcript;
        if (!said.trim()) return;
        liveWrote = true;
        put((base + said).replace(/ {2,}/g, ' '));  // the engine often starts a phrase with a space of its own
      };
      mine.onerror = (e) => {
        if (rec !== mine || e.error === 'no-speech' || e.error === 'aborted') return;
        // no service behind it, or no permission for it: stop using it for good; the recording covers it
        if (e.error === 'network' || e.error === 'service-not-allowed' || e.error === 'language-not-supported') markBroken();
        dropLive();
      };
      mine.onend = () => {
        if (rec !== mine) return;
        if (mode !== 'on') return;
        // the browser ends a session after some silence: carry on listening until the person taps the microphone
        const now = Date.now();
        restarts = restarts.filter((t) => now - t < 3000);
        if (restarts.length >= 4) { dropLive(); return; }
        restarts.push(now);
        base = spaced();
        try { mine.start(); } catch { dropLive(); }
      };
      try { mine.start(); usedLive = true; } catch { dropLive(); }
    }

    // ---------------------------------------------------------------- start / stop
    async function start() {
      mode = 'on'; liveWrote = false; usedLive = false; restarts = []; base = spaced(); startedAt = Date.now();
      ui(true);
      hint('Activando el micrófono…');
      let started = false;
      try {
        recorder = await cadenceRecorder.start({ maxSeconds: 60, onAutoStop: () => { if (mode === 'on') stop(); } });
        started = true;
        level = meter(recorder.stream, (v) => button.style.setProperty('--lvl', v.toFixed(3)));
        button.classList.add('metered');
      } catch (err) { recorder = null; if (!SR || liveBroken()) { mode = 'idle'; ui(false); fail(err.message); return; } }
      if (SR && !liveBroken()) startLive();
      if (mode !== 'on') return;
      clock = setInterval(() => {
        const secs = Math.floor((Date.now() - startedAt) / 1000);
        const quiet = level && secs >= 4 && !liveWrote && level.peak() < 0.015;
        hint(quiet ? 'No detecto tu voz. Revisa que el micrófono correcto esté activo y habla más cerca.'
          : `Te escucho… ${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')} · toca el micrófono para terminar. No se envía solo.`);
      }, 250);
      hint(started ? 'Te escucho… toca el micrófono para terminar. No se envía solo.' : 'Te escucho… (sin respaldo de grabación)');
    }

    async function stop() {
      if (mode !== 'on') return;
      mode = 'working';
      clearInterval(clock); clock = null;
      dropLive();
      if (level) { level.stop(); level = null; }
      button.classList.remove('metered'); button.style.removeProperty('--lvl');
      ui(false, true);
      const r = recorder; recorder = null;
      const wav = r ? await r.stop() : null;
      if (liveWrote) {                                     // the browser wrote it live: that text is already in the box
        mode = 'idle'; ui(false); hint(''); field.focus(); return;
      }
      if (!wav) {
        mode = 'idle'; ui(false);
        fail(usedLive && !r ? 'No alcancé a escucharte. Escribe tu respuesta.' : 'No alcancé a escucharte. Habla un poco más o escribe tu respuesta.');
        return;
      }
      hint('Pasando tu voz a texto…');
      field.disabled = true; field.placeholder = 'Pasando tu voz a texto…';
      try {
        const form = new FormData();
        form.append('audio', wav, 'voz.wav');
        const out = await apiPost('api/transcribe', form, { isFormData: true });
        if (out.text) { put(spaced() + out.text); hint('Léelo, corrígelo y envíalo cuando quieras.'); }
        else fail('No entendí lo que dijiste. Prueba otra vez o escribe tu respuesta.');
      } catch (err) { fail(err.message || 'No pude pasar tu voz a texto. Escribe tu respuesta.'); }
      finally { mode = 'idle'; field.disabled = false; field.placeholder = field.dataset.placeholder || ''; ui(false); field.focus(); }
    }

    function toggle() { if (mode === 'on') stop(); else if (mode === 'idle') start(); }
    button.addEventListener('click', toggle);
    field.addEventListener('input', () => grow(field));
    return { toggle, stop, isOn: () => mode === 'on', grow: () => grow(field) };
  }

  window.cadenceDictation = { attach, supportsLive: Boolean(SR), grow };
})();
