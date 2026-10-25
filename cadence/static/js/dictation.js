// Dictation: the voice becomes TEXT in the message box while the person talks (like Claude does), they read it, fix it and send it
// themselves. Tapping the microphone again stops listening; nothing is ever sent by voice on its own.
//
// 1. Live: the browser's own speech recognition (Chrome, Edge, Opera, Android; Safari partly) writes into the box as they speak.
// 2. Otherwise (iPhone app, Firefox...): records, and on stopping Gemini turns the audio into text that lands in the same box.
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const LANG = (() => { const l = navigator.language || ''; return l.toLowerCase().startsWith('es') ? l : 'es-PA'; })();

  function grow(field) {
    field.style.height = 'auto';
    field.style.height = `${Math.min(field.scrollHeight, 140)}px`;
  }

  // field: the textarea; button: the microphone button; onError(message): shows a message to the person.
  function attach({ field, button, onError, onState, forceFallback = false }) {
    let rec = null;            // live recognition
    let recorder = null;       // fallback recording
    let listening = false;
    let base = '';             // what was already in the box before this listening started
    let restarts = [];
    const live = Boolean(SR) && !forceFallback;
    let useLive = live;

    const ui = (on, busy) => {
      button.classList.toggle('rec', on);
      button.setAttribute('aria-pressed', String(on));
      button.disabled = Boolean(busy);
      if (onState) onState({ on, busy: Boolean(busy) });
    };
    const put = (text) => {
      field.value = text;
      grow(field);
      field.dispatchEvent(new Event('input', { bubbles: true }));
    };
    const spaced = () => (field.value && !/\s$/.test(field.value) ? `${field.value} ` : field.value);

    // ---------------------------------------------------------------- live
    function startLive() {
      rec = new SR();
      rec.lang = LANG;
      rec.continuous = true;
      rec.interimResults = true;
      base = spaced();
      rec.onresult = (e) => {
        let said = '';
        for (let i = 0; i < e.results.length; i += 1) said += e.results[i][0].transcript;
        put((base + said).replace(/ {2,}/g, ' '));  // the engine often starts a phrase with a space of its own
      };
      rec.onerror = (e) => {
        if (e.error === 'no-speech' || e.error === 'aborted') return;
        listening = false;
        if (e.error === 'not-allowed' || e.error === 'service-not-allowed') { ui(false); if (onError) onError('No pude usar el micrófono. Permítelo en los ajustes del navegador o escribe tu respuesta.'); return; }
        // the browser's recognition service is not reachable (or the language is not supported): record and transcribe instead
        useLive = false; ui(false);
        startRecording();
      };
      rec.onend = () => {
        if (!listening) { ui(false); return; }
        // the browser ends a session after some silence: carry on listening until the person taps the microphone
        const now = Date.now();
        restarts = restarts.filter((t) => now - t < 3000);
        if (restarts.length >= 4) { listening = false; ui(false); return; }
        restarts.push(now);
        base = spaced();
        try { rec.start(); } catch { listening = false; ui(false); }
      };
      listening = true;
      ui(true);
      try { rec.start(); } catch { listening = false; ui(false); if (onError) onError('No pude empezar a escucharte. Escribe tu respuesta.'); }
    }

    // ---------------------------------------------------------------- fallback: record, then transcribe
    async function startRecording() {
      try {
        recorder = await cadenceRecorder.start({ maxSeconds: 60, onAutoStop: () => { if (recorder) stopRecording(); } });
        listening = true;
        ui(true);
        field.placeholder = 'Grabando… toca el micrófono para terminar';
      } catch (err) { recorder = null; listening = false; ui(false); if (onError) onError(err.message); }
    }
    async function stopRecording() {
      const r = recorder; recorder = null; listening = false;
      field.placeholder = 'Pasando tu voz a texto…';
      ui(false, true);
      field.disabled = true;
      try {
        const wav = await r.stop();
        if (!wav) { if (onError) onError('No alcancé a escucharte. Habla un poco más o escribe tu respuesta.'); return; }
        const form = new FormData();
        form.append('audio', wav, 'voz.wav');
        const out = await apiPost('api/transcribe', form, { isFormData: true });
        if (out.text) put(spaced() + out.text);
        else if (onError) onError('No entendí lo que dijiste. Prueba otra vez o escribe tu respuesta.');
      } catch (err) { if (onError) onError(err.message || 'No pude pasar tu voz a texto. Escribe tu respuesta.'); }
      finally { field.disabled = false; field.placeholder = field.dataset.placeholder || ''; ui(false, false); field.focus(); }
    }

    function stop() {
      if (recorder) { stopRecording(); return; }
      if (listening) { listening = false; try { rec.stop(); } catch { /* already stopped */ } ui(false); }
    }
    function toggle() {
      if (listening) { stop(); return; }
      if (useLive) startLive(); else startRecording();
    }
    button.addEventListener('click', toggle);
    field.addEventListener('input', () => grow(field));
    return { toggle, stop, isOn: () => listening, live: () => useLive, grow: () => grow(field) };
  }

  window.cadenceDictation = { attach, supportsLive: Boolean(SR), grow };
})();
