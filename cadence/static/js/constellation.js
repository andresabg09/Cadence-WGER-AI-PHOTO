// Welcome screen: a living constellation behind the cadence icon.
// Stars drift and join with thin lines. Move the pointer and they swirl around it; press and hold and it becomes
// a black hole (stars spiral in, an accretion ring glows); let go and a shockwave throws them back out.

// The hero: the real app icon, wrapped by two orbit rings and three tiny moons.
function cadenceHero(size) {
  const ring = size * 0.46;
  return `<div class="hero" data-hero style="width:${size}px;height:${size}px;">
    <svg class="hero-rings" width="${size}" height="${size}" viewBox="0 0 150 150" fill="none" aria-hidden="true">
      <circle cx="75" cy="75" r="68" stroke="rgba(150,140,255,0.16)" stroke-width="1.2"/>
      <circle class="hero-sweep" cx="75" cy="75" r="68" stroke="var(--accent-to)" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="26 402"/>
      <circle class="hero-counter" cx="75" cy="75" r="58" stroke="rgba(150,140,255,0.28)" stroke-width="1" stroke-dasharray="2 9"/>
      <g class="hero-moons"><circle cx="75" cy="7" r="2.6" fill="var(--accent-to)"/><circle cx="143" cy="75" r="1.8" fill="var(--accent-from)"/><circle cx="26" cy="123" r="2.1" fill="#fff" fill-opacity="0.85"/></g>
    </svg>
    <img class="hero-icon" src="static/icons/icon.svg" alt="cadence" width="${Math.round(ring * 1.12)}" height="${Math.round(ring * 1.12)}">
  </div>`;
}

function mountConstellation(host, options = {}) {
  const full = host === document.body; // the whole screen is the sky (events from the whole page)
  const target = full ? document : host;
  const boxOf = () => (full ? { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight } : host.getBoundingClientRect());
  const canvas = document.createElement('canvas');
  canvas.className = full ? 'constellation fixed' : 'constellation';
  canvas.setAttribute('aria-hidden', 'true');
  (full ? document.body : host).prepend(canvas);
  const ctx = canvas.getContext('2d');
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const stars = [];
  const pointer = { x: 0, y: 0, active: false, down: false, since: 0 };
  let W = 0, H = 0, dpr = 1, hero = { x: 0, y: 0 }, palette = null, frame = 0, wave = null, shoot = null, nextShoot = 2.5, last = 0, running = true;

  const rand = (a, b) => a + Math.random() * (b - a);
  const light = () => /light|reading/.test(document.documentElement.getAttribute('data-theme') || '');
  const colors = () => (light()
    ? { a: [96, 72, 214], b: [20, 140, 190], line: [96, 72, 214], glow: [96, 72, 214], k: 0.55 }
    : { a: [196, 186, 255], b: [128, 232, 255], line: [150, 140, 255], glow: [124, 92, 255], k: 1 });

  function spawn(edge) {
    const s = { x: rand(0, W), y: rand(0, H), vx: rand(-0.14, 0.14), vy: rand(-0.14, 0.14), r: rand(0.6, 1.9), tw: rand(0, 6.28), c: Math.random() < 0.55 ? 'a' : 'b' };
    if (edge) { const side = Math.floor(rand(0, 4)); if (side === 0) s.x = 0; else if (side === 1) s.x = W; else if (side === 2) s.y = 0; else s.y = H; }
    return s;
  }

  function resize() {
    const box = boxOf();
    dpr = Math.min(2, window.devicePixelRatio || 1);
    W = box.width; H = box.height;
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = `${W}px`; canvas.style.height = `${H}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const want = Math.round(Math.min(120, Math.max(54, (W * H) / 8500)));
    while (stars.length < want) stars.push(spawn(false));
    stars.length = want;
    const el = host.querySelector('[data-hero]');
    if (el) { const r = el.getBoundingClientRect(); hero = { x: r.left - box.left + r.width / 2, y: r.top - box.top + r.height / 2 }; } else hero = { x: W / 2, y: H * 0.38 };
    palette = colors();
  }

  function where(e) { const box = boxOf(); pointer.x = e.clientX - box.left; pointer.y = e.clientY - box.top; }
  function onMove(e) { where(e); pointer.active = true; }
  function onDown(e) { where(e); pointer.active = true; pointer.down = true; pointer.since = performance.now(); }
  function release() {
    if (pointer.down) wave = { x: pointer.x, y: pointer.y, t: 0, power: Math.min(1, (performance.now() - pointer.since) / 900) };
    pointer.down = false;
  }
  function onLeave() { release(); pointer.active = false; }

  function step(dt, now) {
    const g = palette;
    // fade the previous frame: leaves soft trails (longer while the hole is open)
    ctx.globalCompositeOperation = 'destination-out';
    ctx.fillStyle = `rgba(0,0,0,${pointer.down ? 0.13 : 0.3})`;
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = 'source-over';

    const reach = pointer.down ? 340 : 170;
    const hole = pointer.down ? Math.min(1, (now - pointer.since) / 700) : 0;
    for (const s of stars) {
      // the icon is a quiet sun: a faint swirl around it keeps the sky turning
      let dx = hero.x - s.x, dy = hero.y - s.y, d = Math.hypot(dx, dy) || 1;
      if (d < 300) { const f = (1 - d / 300) * 0.012; s.vx += (-dy / d) * f; s.vy += (dx / d) * f; }
      if (pointer.active) {
        dx = pointer.x - s.x; dy = pointer.y - s.y; d = Math.hypot(dx, dy) || 1;
        if (d < reach) {
          const f = 1 - d / reach;
          const pull = pointer.down ? 0.2 + 0.36 * hole : 0.012;   // hovering only bends them; holding swallows them
          const spin = pointer.down ? 0.5 + 0.5 * hole : 0.09;
          s.vx += (dx / d) * pull * f * f * 2.2 + (-dy / d) * spin * f * 0.34;
          s.vy += (dy / d) * pull * f * f * 2.2 + (dx / d) * spin * f * 0.34;
          if (pointer.down && d < 20) Object.assign(s, spawn(true), { vx: rand(-0.3, 0.3), vy: rand(-0.3, 0.3) }); // swallowed: reborn at the edge
        }
      }
      if (wave) {
        dx = s.x - wave.x; dy = s.y - wave.y; d = Math.hypot(dx, dy) || 1;
        const front = wave.t * 520;
        if (Math.abs(d - front) < 26 && !s.hit) { const k = (3.4 + 3 * wave.power) * (1 - Math.min(1, d / 480)); s.vx += (dx / d) * k; s.vy += (dy / d) * k; s.hit = wave.t; }
        if (s.hit && wave.t - s.hit > 0.2) s.hit = 0;
      }
      const damp = pointer.down ? 0.994 : 0.987;
      s.vx *= damp; s.vy *= damp; s.vy += 0;
      const speed = Math.hypot(s.vx, s.vy);
      if (speed > 5) { s.vx *= 5 / speed; s.vy *= 5 / speed; }
      if (speed < 0.06 && !pointer.down) { s.vx += rand(-0.02, 0.02); s.vy += rand(-0.02, 0.02); }
      s.x += s.vx * dt * 60; s.y += s.vy * dt * 60;
      if (s.x < -10) s.x = W + 10; else if (s.x > W + 10) s.x = -10;
      if (s.y < -10) s.y = H + 10; else if (s.y > H + 10) s.y = -10;
    }

    // constellation lines between near stars (and from the pointer to the stars close to it)
    const L = Math.min(125, Math.max(84, W / 4));
    ctx.lineWidth = 0.7;
    for (let i = 0; i < stars.length; i += 1) {
      const a = stars[i];
      for (let j = i + 1; j < stars.length; j += 1) {
        const b = stars[j];
        const ddx = a.x - b.x, ddy = a.y - b.y;
        if (ddx > L || ddx < -L || ddy > L || ddy < -L) continue;
        const dd = Math.hypot(ddx, ddy);
        if (dd < L) { ctx.strokeStyle = `rgba(${g.line},${((1 - dd / L) * 0.3 * g.k).toFixed(3)})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); }
      }
      if (pointer.active) {
        const pd = Math.hypot(a.x - pointer.x, a.y - pointer.y);
        if (pd < 150) { ctx.strokeStyle = `rgba(${g.b},${((1 - pd / 150) * 0.55 * g.k).toFixed(3)})`; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(pointer.x, pointer.y); ctx.stroke(); }
      }
    }

    // the stars themselves
    for (const s of stars) {
      const tw = 0.5 + 0.5 * Math.sin(now / 700 + s.tw);
      const sp = Math.hypot(s.vx, s.vy);
      const rgb = g[s.c];
      ctx.fillStyle = `rgba(${rgb},${((0.35 + 0.65 * tw) * g.k).toFixed(3)})`;
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r * (1 + Math.min(sp, 3) * 0.18), 0, 6.283); ctx.fill();
      if (s.r > 1.5) { ctx.fillStyle = `rgba(${rgb},${(0.1 * tw * g.k).toFixed(3)})`; ctx.beginPath(); ctx.arc(s.x, s.y, s.r * 4, 0, 6.283); ctx.fill(); }
    }

    // the black hole: dark core, hot rotating ring, soft halo
    if (pointer.active && pointer.down) {
      const R = 10 + 22 * hole;
      const halo = ctx.createRadialGradient(pointer.x, pointer.y, R * 0.6, pointer.x, pointer.y, R * 4.2);
      halo.addColorStop(0, `rgba(${g.glow},${0.45 * g.k})`); halo.addColorStop(1, `rgba(${g.glow},0)`);
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(pointer.x, pointer.y, R * 4.2, 0, 6.283); ctx.fill();
      ctx.fillStyle = light() ? 'rgba(20,16,50,0.92)' : 'rgba(3,3,8,0.95)';
      ctx.beginPath(); ctx.arc(pointer.x, pointer.y, R * 0.78, 0, 6.283); ctx.fill();
      for (let k = 0; k < 3; k += 1) {
        ctx.strokeStyle = `rgba(${k === 1 ? g.a : g.b},${(0.85 - k * 0.22) * g.k})`;
        ctx.lineWidth = 2.2 - k * 0.6;
        ctx.beginPath(); ctx.arc(pointer.x, pointer.y, R * (1 + k * 0.28), now / 260 + k * 2, now / 260 + k * 2 + 4.2); ctx.stroke();
      }
    } else if (pointer.active) {
      const halo = ctx.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 46);
      halo.addColorStop(0, `rgba(${g.glow},${0.22 * g.k})`); halo.addColorStop(1, `rgba(${g.glow},0)`);
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(pointer.x, pointer.y, 46, 0, 6.283); ctx.fill();
    }

    // shockwave ring after release
    if (wave) {
      wave.t += dt;
      const r = wave.t * 520, a = Math.max(0, 1 - wave.t / 0.9);
      ctx.strokeStyle = `rgba(${g.b},${(0.6 * a * g.k).toFixed(3)})`; ctx.lineWidth = 2.2 * a + 0.4;
      ctx.beginPath(); ctx.arc(wave.x, wave.y, r, 0, 6.283); ctx.stroke();
      if (wave.t > 0.9) { wave = null; stars.forEach((s) => { s.hit = 0; }); }
    }

    // now and then, a shooting star
    nextShoot -= dt;
    if (!shoot && nextShoot <= 0) { shoot = { x: rand(W * 0.1, W * 0.9), y: rand(0, H * 0.35), vx: rand(5, 8) * (Math.random() < 0.5 ? 1 : -1), vy: rand(2.5, 4), life: 0 }; nextShoot = rand(5, 10); }
    if (shoot) {
      shoot.life += dt; shoot.x += shoot.vx * dt * 60; shoot.y += shoot.vy * dt * 60;
      const grad = ctx.createLinearGradient(shoot.x, shoot.y, shoot.x - shoot.vx * 9, shoot.y - shoot.vy * 9);
      grad.addColorStop(0, `rgba(${g.b},${0.9 * g.k})`); grad.addColorStop(1, `rgba(${g.b},0)`);
      ctx.strokeStyle = grad; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(shoot.x, shoot.y); ctx.lineTo(shoot.x - shoot.vx * 9, shoot.y - shoot.vy * 9); ctx.stroke();
      if (shoot.life > 1.1 || shoot.x < -60 || shoot.x > W + 60 || shoot.y > H + 60) shoot = null;
    }
  }

  function loop(now) {
    if (!running) return;
    if (!canvas.isConnected) { destroy(); return; }
    const dt = Math.min(0.05, (now - (last || now)) / 1000);
    last = now;
    if (!document.hidden) { if (frame % 90 === 0) palette = colors(); step(dt, now); }
    frame += 1;
    requestAnimationFrame(loop);
  }

  function destroy() {
    running = false;
    target.removeEventListener('pointermove', onMove); target.removeEventListener('pointerdown', onDown);
    target.removeEventListener('pointerup', release); target.removeEventListener('pointercancel', onLeave); target.removeEventListener('pointerleave', onLeave);
    window.removeEventListener('resize', resize);
    canvas.remove();
  }

  resize();
  window.addEventListener('resize', resize);
  if (reduce) {
    step(0.016, 0); // one still frame: the sky without the motion
    return { destroy, refresh: resize, calm() {} };
  }
  target.addEventListener('pointermove', onMove, { passive: true });
  target.addEventListener('pointerdown', onDown, { passive: true });
  target.addEventListener('pointerup', release, { passive: true });
  target.addEventListener('pointercancel', onLeave, { passive: true });
  if (full) document.documentElement.addEventListener('pointerleave', onLeave); else target.addEventListener('pointerleave', onLeave);
  requestAnimationFrame(loop);
  return { destroy, refresh: resize, calm(on) { canvas.style.opacity = on ? '0.25' : '1'; } };
}
