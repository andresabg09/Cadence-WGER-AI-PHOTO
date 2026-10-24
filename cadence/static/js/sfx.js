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

  // A synth pluck: a saw through a closing low-pass, the "sleek / futuristic" voice of the app.
  function pluck(t, freq, dur, o = {}) {
    const { gain = 0.14, from = 4200, to = 500, send = 0.6 } = o;
    const osc = ctx.createOscillator(); const lp = ctx.createBiquadFilter(); const amp = ctx.createGain();
    osc.type = 'sawtooth'; osc.frequency.setValueAtTime(freq, t); osc.detune.value = 6;
    lp.type = 'lowpass'; lp.Q.value = 3;
    lp.frequency.setValueAtTime(from, t); lp.frequency.exponentialRampToValueAtTime(to, t + dur * 0.8);
    amp.gain.setValueAtTime(0.0001, t); amp.gain.exponentialRampToValueAtTime(gain, t + 0.006); amp.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(lp); lp.connect(amp); amp.connect(master);
    if (send) { const r = ctx.createGain(); r.gain.value = send; amp.connect(r); r.connect(reverb); }
    osc.start(t); osc.stop(t + dur + 0.05);
  }

  // A riser: a note that climbs while its filter opens (the build-up of an intro).
  function riser(t, dur, f0, f1, o = {}) {
    const { gain = 0.1, type = 'sawtooth', lp0 = 300, lp1 = 7000 } = o;
    const osc = ctx.createOscillator(); const lp = ctx.createBiquadFilter(); const amp = ctx.createGain();
    osc.type = type; osc.frequency.setValueAtTime(f0, t); osc.frequency.exponentialRampToValueAtTime(f1, t + dur);
    lp.type = 'lowpass'; lp.Q.value = 2; lp.frequency.setValueAtTime(lp0, t); lp.frequency.exponentialRampToValueAtTime(lp1, t + dur);
    amp.gain.setValueAtTime(0.0001, t); amp.gain.exponentialRampToValueAtTime(gain, t + dur * 0.9); amp.gain.exponentialRampToValueAtTime(0.0001, t + dur + 0.04);
    osc.connect(lp); lp.connect(amp); amp.connect(master);
    osc.start(t); osc.stop(t + dur + 0.1);
  }

  const N = (semitones) => 440 * Math.pow(2, semitones / 12); // A4 = 0
  const C5 = N(3), E5 = N(7), G5 = N(10), A5 = N(12), B5 = N(14), C6 = N(15), E6 = N(19); // A4 = 440 Hz

  const SOUNDS = {
    tick(t) { tone(t, 1500, 0.05, { gain: 0.1, send: 0.2 }); },
    open(t) { tone(t, 520, 0.16, { type: 'triangle', glideTo: 820, gain: 0.12, send: 0.5 }); air(t, 0.26, 500, 2600, { gain: 0.05, q: 0.9 }); tone(t + 0.07, 1040, 0.22, { gain: 0.05, bell: true }); },
    close(t) { tone(t, 760, 0.12, { type: 'triangle', glideTo: 420, gain: 0.1, send: 0.3 }); air(t, 0.14, 2000, 500, { gain: 0.03 }); },
    save(t) { [E5, B5, E6].forEach((f, i) => tone(t + i * 0.085, f, 0.9, { gain: 0.2 - i * 0.03, bell: true })); },
    // Adding a food: two quick plucks going up, a touch of glitter.
    add(t) { pluck(t, N(0), 0.22, { gain: 0.13 }); pluck(t + 0.075, N(7), 0.3, { gain: 0.12 }); tone(t + 0.075, N(19), 0.5, { gain: 0.05, bell: true }); air(t + 0.07, 0.07, 6000, 9500, { gain: 0.02, type: 'highpass' }); },
    // Picking one of the options: a clean glass tick.
    pick(t) { tone(t, 1976, 0.07, { gain: 0.1, send: 0.3 }); tone(t, 2637, 0.05, { gain: 0.04, send: 0.3 }); pluck(t, N(-12), 0.1, { gain: 0.06, send: 0.1 }); },
    // Opening the streak panel: an intro. Riser, hit, then a shimmer chord (bigger with a longer streak).
    streakOpen(t, o = {}) {
      const big = (o.days || 0) >= 7;
      riser(t, 0.48, 110, 880, { gain: 0.11 });
      riser(t, 0.48, 220, 1760, { gain: 0.05, type: 'triangle', lp0: 500, lp1: 9000 });
      air(t, 0.5, 1500, 9000, { gain: 0.035, type: 'highpass', q: 0.5 });
      const hit = t + 0.5;
      tone(hit, 78, 0.55, { glideTo: 38, gain: 0.34, send: 0.1 });                  // sub-bass impact
      air(hit, 0.14, 2500, 300, { gain: 0.1, type: 'lowpass', q: 0.7 });          // the thud's air
      [A5, E6, N(24)].forEach((f, i) => tone(hit + 0.02 + i * 0.045, f, 1.5, { gain: 0.17 - i * 0.03, bell: true }));
      tone(hit + 0.02, N(16), 1.4, { gain: 0.08, bell: true });                    // C#6: the major third
      if (big) { tone(hit + 0.2, N(28), 1.6, { gain: 0.09, bell: true }); air(hit + 0.05, 0.9, 6000, 12000, { gain: 0.03, type: 'highpass', q: 0.4 }); }
    },
    // Arriving at a screen: short and quiet, each with its own character.
    // Perfil: a warm hello, two soft notes going up with a speck of glitter.
    enterProfile(t) { tone(t, N(5), 0.55, { type: 'triangle', gain: 0.11, send: 0.6 }); tone(t + 0.1, N(9), 0.7, { type: 'triangle', gain: 0.09, send: 0.6 }); tone(t + 0.11, N(21), 0.7, { gain: 0.04, bell: true }); },
    // Ajustes: a precise little dial, two clicks and a soft low settle.
    enterSettings(t) { tone(t, 1250, 0.04, { gain: 0.09, send: 0.2 }); tone(t + 0.055, 1880, 0.05, { gain: 0.08, send: 0.25 }); pluck(t + 0.11, N(-5), 0.3, { gain: 0.1, send: 0.3 }); },
    // Moving between the main sections. Played on the tap, and the page leaves only after NAV_DELAY, so each one is
    // COMPLETE: it starts, resolves on a last note and dies out on its own in about 0.3 s (nothing is cut by the page
    // change, and almost no reverb, whose tail would be). Keep every note + decay under NAV_DELAY.
    // Progreso: three light notes going up, like a small staircase.
    navProgress(t) {
      tone(t, E5, 0.13, { gain: 0.1, bell: true, send: 0.08 });
      tone(t + 0.05, B5, 0.14, { gain: 0.09, bell: true, send: 0.08 });
      tone(t + 0.1, E6, 0.18, { gain: 0.08, bell: true, send: 0.1 });
    },
    // Retos: a dry little "tok" and a coin-like ding.
    navChallenges(t) {
      pluck(t, N(-7), 0.11, { gain: 0.1, send: 0.05 });
      tone(t + 0.05, 1760, 0.17, { gain: 0.1, bell: true, send: 0.08 });
      tone(t + 0.1, 2349, 0.2, { gain: 0.06, bell: true, send: 0.1 });
    },
    // Premios: a quick shimmer that settles on a bright note.
    navAwards(t) {
      air(t, 0.1, 4500, 9500, { gain: 0.025, type: 'highpass', q: 0.5 });
      tone(t + 0.02, G5, 0.15, { gain: 0.09, bell: true, send: 0.08 });
      tone(t + 0.08, C6, 0.2, { gain: 0.09, bell: true, send: 0.1 });
    },
    // Diario: a warm "welcome back", a bright note that settles a fifth lower.
    navDiary(t) {
      tone(t, G5, 0.12, { gain: 0.09, bell: true, send: 0.08 });
      tone(t + 0.07, C5, 0.2, { type: 'triangle', gain: 0.12, send: 0.1 });
      tone(t + 0.07, C6, 0.17, { gain: 0.05, bell: true, send: 0.08 });
    },
    // Historial: two dry clock ticks and a low, round note, like turning back through pages.
    navHistory(t) {
      tone(t, 1500, 0.04, { gain: 0.07, send: 0.05 });
      tone(t + 0.06, 1180, 0.04, { gain: 0.06, send: 0.05 });
      tone(t + 0.12, N(-5), 0.17, { type: 'triangle', gain: 0.12, send: 0.1 });
      tone(t + 0.12, N(7), 0.15, { gain: 0.05, bell: true, send: 0.08 });
    },
    // Ideas de comidas: a little pop and a sparkle on top, the "light bulb" moment.
    navIdeas(t) {
      tone(t, 620, 0.09, { glideTo: 1500, gain: 0.1, send: 0.1 });
      tone(t + 0.08, E6, 0.2, { gain: 0.09, bell: true, send: 0.1 });
      air(t + 0.08, 0.1, 6000, 11000, { gain: 0.02, type: 'highpass', q: 0.5 });
    },
    // Collecting coins: two bright metallic pings.
    coin(t) { tone(t, 1760, 0.5, { gain: 0.13, bell: true }); tone(t + 0.07, 2637, 0.6, { gain: 0.1, bell: true }); air(t, 0.06, 5000, 9000, { gain: 0.03, type: 'highpass' }); },
    // A new award: a quick rise and a bright chord.
    award(t) { riser(t, 0.16, 400, 1200, { gain: 0.05 }); [C5, G5, C6].forEach((f, i) => tone(t + 0.14 + i * 0.07, f, 1.0, { gain: 0.16 - i * 0.02, bell: true })); tone(t + 0.3, E6, 1.2, { gain: 0.08, bell: true }); },
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

  const BUZZ = { coin: [10, 30, 10], award: [14, 40, 14, 40, 24], navProgress: 8, navChallenges: 8, navAwards: 8, navDiary: 8, navHistory: 8, navIdeas: 8, streakOpen: [12, 70, 40], add: 10, pick: 6, open: 8, save: [14, 40, 14], photo: [10, 30, 18], water: 10, goal: [20, 50, 20, 50, 40], streak: [16, 40, 30], error: [30, 40, 30], remove: 12 };

  function play(name, opts) {
    const s = settings();
    if (!s.on || !SOUNDS[name]) return;
    try { if (navigator.vibrate && BUZZ[name] && navigator.userActivation && navigator.userActivation.hasBeenActive) navigator.vibrate(BUZZ[name]); } catch { /* no haptics */ }
    if (!build()) return;
    if (ctx.state === 'suspended') {
      ctx.resume().catch(() => {});
      // Not allowed yet (no tap on this page): keep it a few seconds and play it at the first tap.
      if (ctx.state === 'suspended') { pending = pending.concat([[name, opts, Date.now()]]).slice(-2); return; }
    }
    SOUNDS[name](ctx.currentTime + 0.01, opts || {});
  }

  // Sound for arriving at a page. A new page only gets to make sound if the browser allows it (the tap that brought us
  // here usually counts); if it does not, say nothing: a welcome that plays at some later tap would be odd.
  function enter(name) {
    const s = settings();
    if (!s.on || !SOUNDS[name]) return;
    try {
      const nav = performance.getEntriesByType('navigation')[0];
      if (nav && nav.type === 'reload') return;
    } catch { /* no navigation timing */ }
    if (!build()) return;
    const started = Date.now();
    const go = () => {
      if (Date.now() - started > 900 || ctx.state !== 'running') return;
      try { if (navigator.vibrate && BUZZ[name] && navigator.userActivation && navigator.userActivation.hasBeenActive) navigator.vibrate(BUZZ[name]); } catch { /* no haptics */ }
      SOUNDS[name](ctx.currentTime + 0.01, {});
    };
    if (ctx.state === 'running') go(); else ctx.resume().then(go).catch(() => {});
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

  // Taps on the main links (Progreso, Retos, Premios, Historial, Ideas, and the way back to the Diario) make their sound
  // first (the tap is what lets the browser play it, a freshly opened page often may not) and the page leaves only after
  // NAV_DELAY, so the sound is whole. The tap is held in the capture phase and replayed afterwards, so the page's own
  // handlers (history.back() on the back arrows, etc.) still do their job.
  const NAV_SOUND = { 'progress.html': 'navProgress', 'challenges.html': 'navChallenges', 'awards.html': 'navAwards', 'history.html': 'navHistory', 'ideas.html': 'navIdeas' };
  const NAV_DELAY = 340; // ms: longer than the longest nav sound including its decay
  let leaving = false;
  let replaying = false;
  const navSoundFor = (a) => {
    if (a.hasAttribute('data-leave') || a.hasAttribute('data-replace')) return null;
    const file = (a.getAttribute('href') || '').split(/[?#]/)[0];
    if (NAV_SOUND[file]) return NAV_SOUND[file];
    // The Diario: only from the side bar and from a page's back arrow (flows have their own exit and stay silent).
    if (file === 'index.html' && (a.closest('.side-nav') || a.getAttribute('aria-label') === 'Volver')) return 'navDiary';
    return null;
  };
  document.addEventListener('click', (e) => {
    if (replaying || leaving || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || (a.target && a.target !== '_self') || a.hasAttribute('download')) return;
    const name = navSoundFor(a);
    if (!name || !settings().on || !(window.AudioContext || window.webkitAudioContext)) return;
    if (a.pathname === location.pathname || (/\/$/.test(location.pathname) && /index\.html$/.test(a.pathname))) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    leaving = true;
    play(name);
    // A quick fade so the short wait reads as a transition, not as lag.
    if (!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches)) document.body.classList.add('nav-leaving');
    setTimeout(() => { replaying = true; try { a.click(); } finally { replaying = false; } }, NAV_DELAY);
    setTimeout(() => { leaving = false; document.body.classList.remove('nav-leaving'); }, 1500); // if the page was kept (bfcache) the next tap works again
  }, true);

  ['pointerdown', 'pointerup', 'touchend', 'click', 'keydown'].forEach((type) => window.addEventListener(type, unlock, { passive: true }));

  window.sfx = {
    play,
    enter,
    unlock,
    isOn: () => settings().on,
    volume: () => settings().volume,
    setOn(on) { save({ on: !!on }); },
    setVolume(v) { save({ volume: Math.max(0, Math.min(1, Number(v))) }); },
  };
})();
