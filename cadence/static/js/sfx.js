// cadence sounds: small, warm, synthesized in the browser (no audio files to download).
// Every sound is a reward or a confirmation, never noise: bells for things you finish, a drop for water,
// a spark for streaks. Volume and mute live in Ajustes (localStorage `cadence_sound`).
(function () {
  const KEY = 'cadence_sound';
  let ctx = null;
  let master = null;
  let reverb = null;
  let pending = [];

  function settings() {
    try { return Object.assign({ on: true, volume: 0.7 }, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch { return { on: true, volume: 0.7 }; }
  }
  function save(patch) {
    try { localStorage.setItem(KEY, JSON.stringify(Object.assign(settings(), patch))); } catch { /* no storage */ }
    if (master) master.gain.value = settings().on ? 0.5 * settings().volume : 0;
  }

  function build() {
    if (ctx) return ctx;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return null;
    ctx = new Ctx();
    master = ctx.createGain();
    master.gain.value = settings().on ? 0.5 * settings().volume : 0;
    const squash = ctx.createDynamicsCompressor();
    squash.threshold.value = -18; squash.ratio.value = 4;
    master.connect(squash); squash.connect(ctx.destination);
    // A short, soft room: decaying noise as an impulse response, mixed in quietly.
    const length = Math.floor(ctx.sampleRate * 1.3);
    const impulse = ctx.createBuffer(2, length, ctx.sampleRate);
    for (let c = 0; c < 2; c += 1) {
      const data = impulse.getChannelData(c);
      for (let i = 0; i < length; i += 1) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 3.2);
    }
    const convolver = ctx.createConvolver();
    convolver.buffer = impulse;
    reverb = ctx.createGain();
    reverb.gain.value = 0.32;
    reverb.connect(convolver); convolver.connect(master);
    return ctx;
  }

  // One note: a sine/triangle with a soft attack and an exponential fade. `bell` adds the inharmonic overtones of a small bell.
  function tone(t, freq, dur, o = {}) {
    const { type = 'sine', gain = 0.22, attack = 0.006, glideTo = null, bell = false, send = 1 } = o;
    const parts = bell ? [[1, 1], [2.76, 0.28], [5.4, 0.1]] : [[1, 1]];
    parts.forEach(([ratio, level]) => {
      const osc = ctx.createOscillator();
      const amp = ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq * ratio, t);
      if (glideTo) osc.frequency.exponentialRampToValueAtTime(glideTo * ratio, t + dur * 0.8);
      amp.gain.setValueAtTime(0.0001, t);
      amp.gain.exponentialRampToValueAtTime(gain * level, t + attack);
      amp.gain.exponentialRampToValueAtTime(0.0001, t + dur / (bell ? Math.sqrt(ratio) : 1));
      osc.connect(amp); amp.connect(master);
      if (send) { const s = ctx.createGain(); s.gain.value = send; amp.connect(s); s.connect(reverb); }
      osc.start(t); osc.stop(t + dur + 0.05);
    });
  }

  // Filtered noise: the air in a shutter, a whoosh, a sparkle.
  function air(t, dur, from, to, o = {}) {
    const { gain = 0.08, q = 1.2, type = 'bandpass' } = o;
    const buf = ctx.createBuffer(1, Math.ceil(ctx.sampleRate * dur), ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i += 1) d[i] = Math.random() * 2 - 1;
    const src = ctx.createBufferSource();
    const filter = ctx.createBiquadFilter();
    const amp = ctx.createGain();
    src.buffer = buf; filter.type = type; filter.Q.value = q;
    filter.frequency.setValueAtTime(from, t);
    filter.frequency.exponentialRampToValueAtTime(to, t + dur);
    amp.gain.setValueAtTime(0.0001, t);
    amp.gain.exponentialRampToValueAtTime(gain, t + Math.min(0.02, dur / 3));
    amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(filter); filter.connect(amp); amp.connect(master);
    src.start(t); src.stop(t + dur + 0.02);
  }

  const N = (semitones) => 440 * Math.pow(2, semitones / 12); // A4 = 0
  const C5 = N(3), E5 = N(7), G5 = N(10), A5 = N(12), B5 = N(14), C6 = N(15), E6 = N(19); // A4 = 440 Hz

  const SOUNDS = {
    tick(t) { tone(t, 1500, 0.05, { gain: 0.1, send: 0.2 }); },
    open(t) { tone(t, 520, 0.16, { type: 'triangle', glideTo: 820, gain: 0.12, send: 0.5 }); air(t, 0.26, 500, 2600, { gain: 0.05, q: 0.9 }); tone(t + 0.07, 1040, 0.22, { gain: 0.05, bell: true }); },
    close(t) { tone(t, 760, 0.12, { type: 'triangle', glideTo: 420, gain: 0.1, send: 0.3 }); air(t, 0.14, 2000, 500, { gain: 0.03 }); },
    save(t) { [E5, B5, E6].forEach((f, i) => tone(t + i * 0.085, f, 0.9, { gain: 0.2 - i * 0.03, bell: true })); },
    shutter(t) { air(t, 0.03, 3600, 2600, { gain: 0.16, q: 2 }); air(t + 0.05, 0.05, 2200, 1500, { gain: 0.1, q: 2 }); },
    photo(t) { air(t, 0.03, 3600, 2600, { gain: 0.16, q: 2 }); air(t + 0.05, 0.05, 2200, 1500, { gain: 0.1, q: 2 }); [E5, B5, E6].forEach((f, i) => tone(t + 0.16 + i * 0.085, f, 0.9, { gain: 0.17 - i * 0.03, bell: true })); },
    water(t) { tone(t, 980, 0.16, { glideTo: 310, gain: 0.26, send: 0.6 }); tone(t + 0.09, 620, 0.1, { glideTo: 1100, gain: 0.09, send: 0.5 }); air(t, 0.05, 2800, 1200, { gain: 0.05 }); },
    goal(t) { [C5, E5, G5, C6, E6].forEach((f, i) => tone(t + i * 0.085, f, 1.2, { gain: 0.2, bell: true })); tone(t + 0.42, C6 * 2, 1.4, { gain: 0.08, bell: true }); air(t + 0.3, 0.9, 5200, 9000, { gain: 0.025, type: 'highpass', q: 0.5 }); },
    streak(t, o = {}) {
      const lift = Math.min(Math.max((o.days || 1) - 1, 0), 12); // longer streak, higher spark
      air(t, 0.32, 3000, 9500, { gain: 0.05, type: 'highpass', q: 0.6 });
      tone(t + 0.04, A5 * Math.pow(2, lift / 12), 1.0, { gain: 0.2, bell: true });
      tone(t + 0.15, E6 * Math.pow(2, lift / 12), 1.2, { gain: 0.18, bell: true });
      if (o.milestone) { tone(t + 0.28, E6 * 1.5 * Math.pow(2, lift / 12), 1.5, { gain: 0.14, bell: true }); tone(t + 0.4, E6 * 2 * Math.pow(2, lift / 12), 1.7, { gain: 0.1, bell: true }); }
    },
    themeDark(t) { tone(t, 330, 0.2, { type: 'triangle', glideTo: 170, gain: 0.16, send: 0.4 }); },
    themeLight(t) { tone(t, 520, 0.28, { glideTo: 880, gain: 0.12, send: 0.7 }); tone(t + 0.06, N(19), 0.5, { gain: 0.07, bell: true }); },
    themeReading(t) { tone(t, 392, 0.3, { type: 'triangle', gain: 0.1, send: 0.6 }); tone(t + 0.08, 494, 0.4, { type: 'triangle', gain: 0.08, send: 0.6 }); },
    toggleOn(t) { tone(t, 700, 0.07, { gain: 0.12, send: 0.3 }); tone(t + 0.06, 1050, 0.1, { gain: 0.1, send: 0.4 }); },
    toggleOff(t) { tone(t, 900, 0.07, { gain: 0.1, send: 0.2 }); tone(t + 0.06, 600, 0.1, { gain: 0.08, send: 0.2 }); },
    scan(t) { tone(t, 1760, 0.09, { type: 'square', gain: 0.045, send: 0.2 }); tone(t + 0.1, 2349, 0.12, { type: 'square', gain: 0.04, send: 0.2 }); },
    recStart(t) { tone(t, 600, 0.09, { gain: 0.14 }); tone(t + 0.08, 900, 0.14, { gain: 0.12, bell: true }); },
    recStop(t) { tone(t, 900, 0.09, { gain: 0.12 }); tone(t + 0.08, 600, 0.14, { gain: 0.1, bell: true }); },
    remove(t) { tone(t, 440, 0.12, { type: 'triangle', glideTo: 250, gain: 0.13, send: 0.2 }); },
    error(t) { tone(t, 247, 0.22, { gain: 0.14 }); tone(t + 0.13, 196, 0.3, { gain: 0.13 }); },
  };

  const BUZZ = { open: 8, save: [14, 40, 14], photo: [10, 30, 18], water: 10, goal: [20, 50, 20, 50, 40], streak: [16, 40, 30], error: [30, 40, 30], remove: 12 };

  function play(name, opts) {
    const s = settings();
    if (!s.on || !SOUNDS[name]) return;
    try { if (navigator.vibrate && BUZZ[name]) navigator.vibrate(BUZZ[name]); } catch { /* no haptics */ }
    if (!build()) return;
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
      // Not allowed yet (no tap on this page): keep it a few seconds and play it at the first tap.
      if (ctx.state === 'suspended') { pending = pending.concat([[name, opts, Date.now()]]).slice(-2); return; }
    }
    SOUNDS[name](ctx.currentTime + 0.01, opts || {});
  }

  function unlock() {
    if (!build()) return;
    const flush = () => {
      const now = Date.now();
      const list = pending.filter((p) => now - p[2] < 6000);
      pending = [];
      list.forEach(([name, opts]) => SOUNDS[name](ctx.currentTime + 0.01, opts || {}));
    };
    if (ctx.state === 'suspended') ctx.resume().then(flush).catch(() => {}); else flush();
  }

  ['pointerdown', 'keydown', 'touchstart'].forEach((type) => window.addEventListener(type, unlock, { passive: true }));

  window.sfx = {
    play,
    unlock,
    isOn: () => settings().on,
    volume: () => settings().volume,
    setOn(on) { save({ on: !!on }); },
    setVolume(v) { save({ volume: Math.max(0, Math.min(1, Number(v))) }); },
  };
})();
