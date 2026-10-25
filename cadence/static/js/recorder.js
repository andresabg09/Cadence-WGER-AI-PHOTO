// Records the microphone and returns a plain 16 kHz mono WAV (browsers record webm/opus or mp4/aac; every model reads WAV).
(function () {
  async function toWav(blob) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    ctx.close();
    const rate = 16000;
    const offline = new OfflineAudioContext(1, Math.max(1, Math.ceil(decoded.duration * rate)), rate);
    const src = offline.createBufferSource();
    src.buffer = decoded;
    src.connect(offline.destination);
    src.start();
    const pcm = (await offline.startRendering()).getChannelData(0);
    const out = new DataView(new ArrayBuffer(44 + pcm.length * 2));
    const text = (at, s) => { for (let i = 0; i < s.length; i += 1) out.setUint8(at + i, s.charCodeAt(i)); };
    text(0, 'RIFF'); out.setUint32(4, 36 + pcm.length * 2, true); text(8, 'WAVE'); text(12, 'fmt ');
    out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, 1, true);
    out.setUint32(24, rate, true); out.setUint32(28, rate * 2, true); out.setUint16(32, 2, true); out.setUint16(34, 16, true);
    text(36, 'data'); out.setUint32(40, pcm.length * 2, true);
    for (let i = 0; i < pcm.length; i += 1) out.setInt16(44 + i * 2, Math.max(-1, Math.min(1, pcm[i])) * 0x7fff, true);
    return new Blob([out], { type: 'audio/wav' });
  }

  const supported = () => Boolean(navigator.mediaDevices && window.MediaRecorder);

  // start() asks for the microphone and begins; the returned object has stop() -> Promise<Blob wav|null> and cancel().
  // Throws an Error with a message fit for the person when the microphone cannot be used.
  async function start({ maxSeconds = 60, onTick, onAutoStop } = {}) {
    if (!supported()) throw new Error('Este navegador no puede grabar audio. Escribe tu respuesta.');
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
    catch { throw new Error('No pude usar el micrófono. Permítelo en los ajustes del navegador o escribe tu respuesta.'); }
    const chunks = [];
    const recorder = new MediaRecorder(stream);
    let cancelled = false;
    const startedAt = Date.now();
    recorder.addEventListener('dataavailable', (e) => { if (e.data && e.data.size) chunks.push(e.data); });
    const release = () => { stream.getTracks().forEach((t) => t.stop()); clearInterval(timer); };
    let finish = null;
    const done = new Promise((resolve) => { finish = resolve; });
    recorder.addEventListener('stop', async () => {
      release();
      if (cancelled || Date.now() - startedAt < 700 || !chunks.length) { finish(null); return; }
      try { finish(await toWav(new Blob(chunks, { type: recorder.mimeType || 'audio/webm' }))); } catch { finish(null); }
    });
    const timer = setInterval(() => {
      const s = Math.floor((Date.now() - startedAt) / 1000);
      if (onTick) onTick(s);
      if (s >= maxSeconds && recorder.state === 'recording') { recorder.stop(); if (onAutoStop) onAutoStop(); }
    }, 250);
    recorder.start();
    return {
      stream,
      stop() { if (recorder.state !== 'inactive') recorder.stop(); return done; },
      cancel() { cancelled = true; if (recorder.state !== 'inactive') recorder.stop(); else release(); },
    };
  }

  window.cadenceRecorder = { toWav, start, supported };
})();
