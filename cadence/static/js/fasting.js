// Fasting on Hoy (Block 17, 17 nov 2026): the card at the top of the day and its sheets.
//   cadenceFasting.mount(el, { today, mealJustSaved })  - paints the card (only for today; another day hides it)
// Plans 12:12 to 18:6 or one's own (12-18 h). The calorie goal never changes because of a fast, and nothing rewards fasting
// longer than the plan. Stages are approximate; autophagy has no hour. Blocked for health reasons = a kind card, no timer.
// Every sheet uses pushOverlay/dismissOverlay, so the system Back button closes it and stays on Hoy.
(function () {
  const ic = (name) => (window.cadenceIcons ? cadenceIcons.icon(name) : '');
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const HIDE_KEY = 'cadence_fast_new_hidden';
  let el = null;
  let state = null;
  let timer = null;
  let opts = {};

  // ---------------------------------------------------------------- time helpers
  const pad = (n) => String(n).padStart(2, '0');
  const hhmm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  function dayWord(d) {
    const now = new Date();
    const diff = Math.round((new Date(dayKey(d)) - new Date(dayKey(now))) / 86400000);
    if (diff === 0) return 'Hoy';
    if (diff === -1) return 'Ayer';
    if (diff === 1) return 'Mañana';
    return d.toLocaleDateString('es', { weekday: 'short', day: 'numeric' });
  }
  const when = (iso) => { const d = new Date(iso); return `${dayWord(d)} ${hhmm(d)}`; };
  function span(ms) {
    const m = Math.max(0, Math.round(ms / 60000));
    const h = Math.floor(m / 60);
    return h ? `${h} h ${pad(m % 60)} min` : `${m} min`;
  }
  const clock = (ms) => { const m = Math.max(0, Math.floor(ms / 60000)); return `${Math.floor(m / 60)}:${pad(m % 60)}`; };
  // The device's own clock, sent with its zone: the server never has to guess which timezone a bare hour meant.
  const localIso = (day, time) => new Date(`${day}T${time}`).toISOString();

  // ---------------------------------------------------------------- sheets
  function sheet(html, bind, cls) {
    const scrim = document.createElement('div');
    scrim.className = 'sheet-scrim';
    const box = document.createElement('div');
    box.className = `entry-sheet fast-sheet ${cls || ''}`;
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.innerHTML = html;
    document.body.append(scrim, box);
    pushOverlay(() => { scrim.remove(); box.remove(); });
    scrim.addEventListener('click', () => dismissOverlay());
    box.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => dismissOverlay()));
    bind(box, (after) => dismissOverlay(after));
    return box;
  }
  const head = (kicker, title) => `<div class="fs-head"><div><div class="fs-kick mono">${kicker}</div><h3 class="disp">${title}</h3></div><button type="button" class="icon-btn" data-close aria-label="Cerrar">${ic('x')}</button></div>`;

  async function call(fn) {
    try {
      const fresh = await fn();
      if (window.swrClear) swrClear('api/fasting');
      state = fresh;
      paint();
      return fresh;
    } catch (err) {
      showToast(err.message);
      throw err;
    }
  }

  // Plans: the five agreed ones, or one's own from 12 to 18 h, and the hour it starts.
  function openPlans() {
    const p = state.plan;
    let hours = p.hours;
    let start = p.start;
    const groups = {};
    state.plans.forEach((x) => { (groups[x.group] = groups[x.group] || []).push(x); });
    const box = sheet(`
      ${head('TU AYUNO', 'Elige tu plan')}
      ${Object.entries(groups).map(([g, list]) => `<div class="fs-group"><b>${g}</b><div class="fs-plans">${list.map((x) => `<button type="button" class="fs-plan" data-h="${x.hours}"><span class="disp">${x.label}</span><small>${x.hours} h ayuno · ${24 - x.hours} h comida</small></button>`).join('')}</div></div>`).join('')}
      <div class="fs-group"><b>A tu medida</b><div class="fs-custom" id="fsCustom"><button type="button" class="step-btn" data-d="-1" aria-label="Una hora menos">${ic('minus')}</button><span class="disp" id="fsCustomLabel"></span><button type="button" class="step-btn" data-d="1" aria-label="Una hora más">${ic('plus')}</button></div><small class="fs-hint">Entre ${state.range[0]} y ${state.range[1]} horas de ayuno</small></div>
      <div class="fs-group"><b>¿A qué hora empiezas a ayunar?</b><div class="chips fs-hours">${['18:00', '19:00', '20:00', '21:00', '22:00'].map((h) => `<button type="button" class="chip" data-start="${h}">${h}</button>`).join('')}<label class="chip fs-other">Otra <input type="time" id="fsOther" aria-label="Otra hora"></label></div></div>
      <p class="fs-note" id="fsSummary"></p>
      <p class="fs-note soft">Tu meta de calorías no cambia: el ayuno solo ordena tus horas.${state.active ? ' Tienes un ayuno en curso: el cambio vale para el siguiente.' : ''}</p>
      <div class="sheet-actions"><button type="button" class="btn-primary" id="fsSave">Guardar plan</button></div>`, (box, close) => {
      const paintPlans = () => {
        box.querySelectorAll('.fs-plan').forEach((b) => b.classList.toggle('on', Number(b.dataset.h) === hours));
        const custom = !state.plans.some((x) => x.hours === hours);
        box.querySelector('#fsCustom').classList.toggle('on', custom);
        box.querySelector('#fsCustomLabel').textContent = `${hours}:${24 - hours}`;
        box.querySelectorAll('[data-start]').forEach((b) => b.classList.toggle('on', b.dataset.start === start));
        const [hh, mm] = start.split(':').map(Number);
        const end = `${pad((hh + hours) % 24)}:${pad(mm)}`;
        box.querySelector('#fsSummary').textContent = `Ayunas de ${start} a ${end} y comes de ${end} a ${start}.`;
      };
      box.querySelectorAll('.fs-plan').forEach((b) => b.addEventListener('click', () => { hours = Number(b.dataset.h); if (window.sfx) sfx.play('pick'); paintPlans(); }));
      box.querySelectorAll('[data-d]').forEach((b) => b.addEventListener('click', () => { hours = Math.max(state.range[0], Math.min(state.range[1], hours + Number(b.dataset.d))); paintPlans(); }));
      box.querySelectorAll('[data-start]').forEach((b) => b.addEventListener('click', () => { start = b.dataset.start; paintPlans(); }));
      box.querySelector('#fsOther').addEventListener('change', (e) => { if (e.target.value) { start = e.target.value; paintPlans(); } });
      box.querySelector('#fsSave').addEventListener('click', async () => {
        await call(() => apiPut('api/fasting/plan', { hours, start }));
        if (window.sfx) sfx.play('save');
        close(() => showToast(`Plan ${hours}:${24 - hours} guardado`, 'ok'));
      });
      paintPlans();
    });
    return box;
  }

  // "Antes de empezar": the safety list first, then what helps (eat before, drink, hunger, water), all with icons.
  const STEPS = [
    { kick: 'ANTES DE EMPEZAR', icon: 'shield-check', title: 'El ayuno no es para todas las personas', safety: true,
      lines: ['Tienes menos de 18 años', 'Estás embarazada o das pecho', 'Tienes diabetes o tomas medicinas que bajan el azúcar', 'Has tenido un trastorno de la alimentación o tu peso está bajo'] },
    { kick: 'PASO 1 · A COMER', icon: 'bowl-steam', title: '¿Comiste hace poco?', lines: ['Empieza el ayuno después de una comida completa', 'La proteína y la fibra te ayudan a aguantar mejor', '¿Poco tiempo? Un bocado ligero también sirve'] },
    { kick: 'PASO 2 · BEBE', icon: 'coffee', title: 'Mientras ayunas, bebe', lines: ['Agua, con o sin gas', 'Café o té, sin azúcar ni leche', 'Lo demás con calorías rompe el ayuno: no pasa nada, solo anótalo'] },
    { kick: 'PASO 3 · EL HAMBRE', icon: 'hand-heart', title: 'El hambre llega en olas y pasa', lines: ['Es normal sentir hambre, sobre todo los primeros días', 'Bebe algo y distráete: camina, escucha música, lee', 'Si te mareas, tiemblas o te sientes mal: come. Siempre.'], warnLast: true },
    { kick: 'PASO 4 · TU AGUA', icon: 'drop', title: 'Tus vasos de agua cuentan', lines: ['Toca un vaso en Hoy cada vez que bebas', 'Tu meta de agua es la misma de siempre', 'Los avisos te recuerdan beber, si los activas'] },
    { kick: 'LISTO', icon: 'timer', title: 'Empieza suave', lines: ['Un plan de 12:12 o 14:10 es un buen comienzo', 'El ayuno ordena tus horas; tus calorías siguen mandando', 'Terminar antes nunca es un error: queda guardado igual'] },
  ];
  function openIntro() {
    let step = 0;
    sheet('<div id="fiBody"></div>', (box, close) => {
      const body = box.querySelector('#fiBody');
      const render = () => {
        const s = STEPS[step];
        body.innerHTML = `
          <div class="fi-bar">${STEPS.map((_, i) => `<span class="${i <= step ? 'on' : ''}"></span>`).join('')}</div>
          <div class="fi-top"><button type="button" class="icon-btn" id="fiBack" aria-label="Atrás" ${step ? '' : 'disabled'}>${ic('caret-left')}</button><button type="button" class="icon-btn" data-close aria-label="Cerrar">${ic('x')}</button></div>
          <div class="fi-art" aria-hidden="true">${ic(s.icon)}</div>
          <div class="fs-kick mono">${s.kick}</div>
          <h3 class="disp fi-title">${s.title}</h3>
          <ul class="fi-lines">${s.lines.map((l, i) => `<li class="${s.safety || (s.warnLast && i === s.lines.length - 1) ? 'warn' : ''}">${ic(s.safety ? 'warning-circle' : 'check')}<span>${esc(l)}</span></li>`).join('')}</ul>
          <div class="sheet-actions fi-actions">
            ${s.safety ? '<button type="button" class="btn-secondary" id="fiSome">Alguna me aplica</button><button type="button" class="btn-primary" id="fiNone">Ninguna me aplica</button>'
              : `<button type="button" class="btn-primary" id="fiNext">${step === STEPS.length - 1 ? 'Elegir mi plan' : 'Continuar'}</button>`}
          </div>`;
        body.querySelector('[data-close]').addEventListener('click', () => dismissOverlay());
        const back = body.querySelector('#fiBack');
        if (back) back.addEventListener('click', () => { step = Math.max(0, step - 1); render(); });
        const next = body.querySelector('#fiNext');
        if (next) next.addEventListener('click', () => {
          if (step === STEPS.length - 1) { close(() => openPlans()); return; }
          step += 1;
          if (window.sfx) sfx.play('pick');
          render();
        });
        const none = body.querySelector('#fiNone');
        if (none) none.addEventListener('click', async () => { await call(() => apiPost('api/fasting/intro', { none_apply: true })); step = 1; render(); });
        const some = body.querySelector('#fiSome');
        if (some) some.addEventListener('click', async () => { await call(() => apiPost('api/fasting/intro', { none_apply: false })); close(() => openBlocked()); });
      };
      render();
    }, 'fast-intro');
  }

  function openBlocked() {
    const self = state.blocked === 'self';
    sheet(`
      ${head('TU SALUD PRIMERO', 'El ayuno no es para ti por ahora')}
      <div class="fi-art small" aria-hidden="true">${ic('hand-heart')}</div>
      <p class="fs-note">${esc(state.blocked_text || '')} No hiciste nada mal: así te cuidamos.</p>
      <div class="fs-box"><b>Lo que sí te ayuda, y ya está en cadence</b><span>Registrar tus comidas con foto, código o voz</span><span>Comer a horas parecidas cada día, sin saltarte comidas</span><span>Tus vasos de agua y tus retos de constancia</span></div>
      ${self ? '<p class="fs-note soft">¿Ya no aplica nada de esa lista? Vuelve a revisarla.</p>' : '<p class="fs-note soft">Si algo cambió, actualiza tus datos de salud en Perfil · Objetivos.</p>'}
      <div class="sheet-actions">${self ? '<button type="button" class="btn-secondary" id="fbAgain">Revisar la lista</button>' : ''}<button type="button" class="btn-primary" data-close>Entendido</button></div>`, (box, close) => {
      const again = box.querySelector('#fbAgain');
      if (again) again.addEventListener('click', () => close(() => openIntro()));
    });
  }

  // Estado de tu cuerpo: the stages in a row; the one you are in has a ring. Approximate, with sources.
  function openBody(focus) {
    const hours = state.active ? state.active.hours : 0;
    const now = state.active ? state.active.stage : -1;
    let pick = focus != null ? focus : Math.max(0, now);
    sheet(`${head('TU AYUNO', 'Estado de tu cuerpo')}<div id="fbBody"></div>`, (box) => {
      const body = box.querySelector('#fbBody');
      const render = () => {
        const s = state.stages[pick];
        body.innerHTML = `
          <div class="fb-row" role="tablist">${state.stages.map((x, i) => `<button type="button" role="tab" aria-selected="${i === pick}" class="fb-stage${i === pick ? ' pick' : ''}${i <= now ? ' done' : ''}" data-i="${i}" aria-label="${esc(x.title)}"><span>${ic(x.icon)}</span><small class="mono">${x.from_h} h</small></button>`).join('')}</div>
          ${pick === now ? '<span class="fb-now mono">AHORA ESTÁS AQUÍ</span>' : ''}
          <h3 class="disp fb-title">${esc(s.title)}</h3>
          <div class="fb-when">${ic('timer')}<span>${s.from_h ? `Desde unas ${s.from_h} h después de tu última comida (aprox.)` : 'Justo después de comer'}</span></div>
          <p class="fs-note">${esc(s.body)}</p>
          <p class="fs-note soft">Las horas cambian de una persona a otra: dependen de lo que comiste, de cuánto te mueves y de tu cuerpo. Son una guía, no una promesa.</p>
          <div class="fs-box"><b>¿Y la autofagia?</b><span>Es real: las células reciclan sus partes viejas. Pero en personas todavía no se sabe a qué hora del ayuno empieza ni cuánto aumenta; los números que circulan salen de estudios en animales. Por eso no te la mostramos con una hora.</span></div>
          <div class="fs-box warn"><b>Para y come si sientes</b><span>Mareo, temblor, confusión, el corazón acelerado o que te vas a desmayar. Terminar antes nunca es un error.</span></div>
          <div class="fb-sources"><span class="mono">FUENTES</span>${state.sources.map((x) => `<span>${esc(x)}</span>`).join('')}</div>
          ${hours ? `<p class="fs-note soft">Llevas ${span(hours * 3600000)} de ayuno.</p>` : ''}`;
        body.querySelectorAll('[data-i]').forEach((b) => b.addEventListener('click', () => { pick = Number(b.dataset.i); render(); }));
      };
      render();
    });
  }

  // Edit a time: day (Hoy / Ayer) + hour. Never in the future (the server checks it too).
  function openTime(title, iso, onSave) {
    const d = iso ? new Date(iso) : new Date();
    const today = new Date();
    const yesterday = new Date(today.getTime() - 86400000);
    let day = dayKey(d);
    sheet(`
      ${head('TU AYUNO', esc(title))}
      <div class="chips" style="margin-bottom:12px;">${[[dayKey(yesterday), 'Ayer'], [dayKey(today), 'Hoy']].map(([k, l]) => `<button type="button" class="chip${k === day ? ' on' : ''}" data-day="${k}">${l}</button>`).join('')}</div>
      <label class="field"><span>HORA</span><input class="input" type="time" id="ftTime" value="${hhmm(d)}"></label>
      <div class="form-error" id="ftErr"></div>
      <div class="sheet-actions"><button type="button" class="btn-primary" id="ftSave">Guardar</button></div>`, (box, close) => {
      box.querySelectorAll('[data-day]').forEach((b) => b.addEventListener('click', () => { day = b.dataset.day; box.querySelectorAll('[data-day]').forEach((x) => x.classList.toggle('on', x === b)); }));
      box.querySelector('#ftSave').addEventListener('click', async () => {
        const t = box.querySelector('#ftTime').value;
        if (!t) return;
        try { await onSave(localIso(day, t)); close(); } catch (err) { const e = box.querySelector('#ftErr'); e.textContent = err.message; e.classList.add('show'); }
      });
    });
  }

  function openPast() {
    const today = new Date();
    const yesterday = new Date(today.getTime() - 86400000);
    const twoAgo = new Date(today.getTime() - 2 * 86400000);
    const days = [[dayKey(twoAgo), 'Antier'], [dayKey(yesterday), 'Ayer'], [dayKey(today), 'Hoy']];
    let startDay = days[1][0];
    let endDay = days[2][0];
    const dayChips = (name, current) => days.map(([k, l]) => `<button type="button" class="chip${k === current ? ' on' : ''}" data-${name}="${k}">${l}</button>`).join('');
    sheet(`
      ${head('TU AYUNO', 'Agregar un ayuno pasado')}
      <b class="fs-label">Empezó</b><div class="chips">${dayChips('sd', startDay)}</div>
      <label class="field"><span>HORA</span><input class="input" type="time" id="fpStart" value="20:00"></label>
      <b class="fs-label">Terminó</b><div class="chips">${dayChips('ed', endDay)}</div>
      <label class="field"><span>HORA</span><input class="input" type="time" id="fpEnd" value="10:00"></label>
      <div class="form-error" id="fpErr"></div>
      <div class="sheet-actions"><button type="button" class="btn-primary" id="fpSave">Guardar ayuno</button></div>`, (box, close) => {
      const wire = (attr, set) => box.querySelectorAll(`[data-${attr}]`).forEach((b) => b.addEventListener('click', () => {
        set(b.dataset[attr]);
        box.querySelectorAll(`[data-${attr}]`).forEach((x) => x.classList.toggle('on', x === b));
      }));
      wire('sd', (v) => { startDay = v; });
      wire('ed', (v) => { endDay = v; });
      box.querySelector('#fpSave').addEventListener('click', async () => {
        try {
          await call(() => apiPost('api/fasting/past', { start: localIso(startDay, box.querySelector('#fpStart').value), end: localIso(endDay, box.querySelector('#fpEnd').value) }));
          if (window.sfx) sfx.play('save');
          close(() => showToast('Ayuno guardado', 'ok'));
        } catch (err) { const e = box.querySelector('#fpErr'); e.textContent = err.message; e.classList.add('show'); }
      });
    });
  }

  function openHistory() {
    const rows = state.history.map((f) => `
      <div class="fh-row"><div><b>${when(f.started_at)} → ${f.ended_at ? when(f.ended_at) : '…'}</b><small>${span(f.hours * 3600000)} de ${f.planned_h} h ${f.complete ? '· completo' : ''}</small></div>
      <button type="button" class="icon-btn" data-edit="${f.id}" aria-label="Editar">${ic('pencil-simple')}</button><button type="button" class="icon-btn" data-del="${f.id}" aria-label="Borrar">${ic('trash')}</button></div>`).join('');
    sheet(`${head('TU AYUNO', 'Tus ayunos')}<p class="fs-note soft">Esta semana: ${state.week.done} completos de ${state.week.days} días.</p><div class="fh-list">${rows || '<p class="fs-note soft">Todavía no hay ayunos terminados.</p>'}</div>
      <div class="sheet-actions"><button type="button" class="btn-secondary" id="fhPast">Agregar uno pasado</button></div>`, (box, close) => {
      box.querySelector('#fhPast').addEventListener('click', () => close(() => openPast()));
      box.querySelectorAll('[data-del]').forEach((b) => {
        let armed = false;
        b.addEventListener('click', async () => {
          if (!armed) { armed = true; b.classList.add('armed'); showToast('Toca otra vez para borrarlo', 'warn'); return; }
          await call(() => apiDelete(`api/fasting/${b.dataset.del}`));
          close(() => showToast('Ayuno borrado', 'ok'));
        });
      });
      box.querySelectorAll('[data-edit]').forEach((b) => b.addEventListener('click', () => {
        const f = state.history.find((x) => String(x.id) === b.dataset.edit);
        close(() => openTime('Hora en que terminó', f.ended_at, (iso) => call(() => apiPatch(`api/fasting/${f.id}`, { end: iso }))));
      }));
    });
  }

  function askEndAfterMeal() {
    sheet(`
      ${head('COMISTE', '¿Terminas tu ayuno?')}
      <p class="fs-note">Registraste una comida mientras tu ayuno seguía abierto. Si ya comiste, termínalo; si solo fue algo sin calorías, sigue igual.</p>
      <div class="sheet-actions"><button type="button" class="btn-secondary" data-close>Sigo en ayuno</button><button type="button" class="btn-primary" id="fmEnd">Terminar ahora</button></div>`, (box, close) => {
      box.querySelector('#fmEnd').addEventListener('click', () => close(() => endNow()));
    });
  }

  async function endNow(iso) {
    const fresh = await call(() => apiPost('api/fasting/end', iso ? { at: iso } : {}));
    const done = fresh.ended;
    if (done && done.complete) {
      if (window.sfx) sfx.play('goal');
      showToast(`¡Ayuno completo! ${span(done.hours * 3600000)}`, 'ok');
    } else if (done) {
      if (window.sfx) sfx.play('save');
      showToast(`Ayuno guardado: ${span(done.hours * 3600000)}. Terminar antes también cuenta.`, 'ok');
    }
  }

  async function startNow() {
    if (!state.plan.intro_done) { openIntro(); return; }
    await call(() => apiPost('api/fasting/start', {}));
    if (window.sfx) sfx.play('streak');
    showToast(`Empezó tu ayuno ${state.plan.label}`, 'ok');
  }

  // ---------------------------------------------------------------- the card
  function ring(progress, markers) {
    const r = 94;
    const c = 2 * Math.PI * r;
    const dots = markers.map((m) => {
      const a = (m.at * 360 - 90) * (Math.PI / 180);
      const x = 110 + r * Math.cos(a);
      const y = 110 + r * Math.sin(a);
      return `<g class="fc-mark${m.done ? ' done' : ''}" transform="translate(${x.toFixed(1)} ${y.toFixed(1)})"><circle r="11"/><g transform="translate(-7 -7) scale(0.0547)">${ic(m.icon).replace(/^<svg[^>]*>|<\/svg>$/g, '')}</g></g>`;
    }).join('');
    return `<svg class="fc-ring" viewBox="0 0 220 220" aria-hidden="true"><defs><linearGradient id="fcg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color: var(--accent-from)"/><stop offset="1" style="stop-color: var(--accent-to)"/></linearGradient></defs>
      <circle cx="110" cy="110" r="${r}" class="fc-track"/><circle cx="110" cy="110" r="${r}" class="fc-fill" stroke-dasharray="${(c * Math.min(1, progress)).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 110 110)"/>${dots}</svg>`;
  }

  function paint() {
    if (!el) return;
    clearInterval(timer);
    if (!opts.today || !state) { el.hidden = true; return; }
    el.hidden = false;
    const s = state;
    if (s.blocked) {
      el.innerHTML = `<div class="fc-blocked">${ic('hand-heart')}<div><b>Ayuno no disponible para ti</b><small>Por tu salud, cadence no lo ofrece ahora.</small></div><button type="button" class="btn-secondary fc-small" id="fcWhy">Por qué</button></div>`;
      el.querySelector('#fcWhy').addEventListener('click', openBlocked);
      return;
    }
    if (!s.plan.intro_done && !s.active) {
      let hidden = false;
      try { hidden = localStorage.getItem(HIDE_KEY) === '1'; } catch { /* no storage */ }
      if (hidden) {
        el.innerHTML = `<button type="button" class="fc-mini" id="fcIntro">${ic('timer')}<span>Ayuno con horario</span>${ic('caret-down')}</button>`;
        el.querySelector('#fcIntro').addEventListener('click', openIntro);
        return;
      }
      el.innerHTML = `<div class="fc-new"><div class="fc-new-ico">${ic('timer')}</div><div class="fc-new-text"><span class="mono">NUEVO</span><b>Ayuno con horario</b><small>Ordena a qué hora comes. Tu meta de calorías no cambia.</small></div>
        <div class="fc-new-actions"><button type="button" class="btn-secondary fc-small" id="fcLater">Ahora no</button><button type="button" class="btn-primary fc-small" id="fcIntro">Conocerlo</button></div></div>`;
      el.querySelector('#fcIntro').addEventListener('click', openIntro);
      el.querySelector('#fcLater').addEventListener('click', () => { try { localStorage.setItem(HIDE_KEY, '1'); } catch { /* */ } paint(); });
      return;
    }
    const a = s.active;
    const planned = a ? a.planned_h : s.plan.hours;
    const markers = s.stages.filter((x) => x.from_h > 0 && x.from_h < planned).map((x, i) => ({ at: x.from_h / planned, icon: x.icon, done: a && a.hours >= x.from_h, i }));
    el.innerHTML = `
      <div class="fc-head"><span class="mono fc-state">${a ? 'AYUNANDO' : 'VENTANA PARA COMER'}</span>
        <div class="fc-head-actions"><button type="button" class="fc-plan" id="fcPlan">Mi plan <b class="mono">${a ? `${Math.round(a.planned_h)}:${24 - Math.round(a.planned_h)}` : s.plan.label}</b>${ic('pencil-simple')}</button><button type="button" class="icon-btn" id="fcHist" aria-label="Tus ayunos">${ic('list-checks')}</button></div></div>
      <div class="fc-ring-wrap">${ring(0, markers)}<div class="fc-center"><span class="fc-top" id="fcTop"></span><span class="disp fc-big" id="fcBig"></span><span class="fc-small-text" id="fcSmall"></span></div></div>
      ${a ? `<button type="button" class="fc-stage" id="fcStage"><i></i><span id="fcStageText"></span>${ic('caret-down')}</button>` : '<button type="button" class="fc-stage" id="fcStage"><i></i><span>Cómo funciona cada etapa</span></button>'}
      ${a && a.overdue ? '<div class="fc-overdue">¿Olvidaste terminarlo? Lleva más de 24 horas abierto. <button type="button" class="linkish" id="fcFix">Terminarlo a otra hora</button></div>' : ''}
      <div class="fc-times">
        <button type="button" class="fc-time" id="fcStart"><span class="mono">INICIO</span><b>${a ? when(a.started_at) : when(s.next_start)}</b></button>
        <button type="button" class="fc-time" id="fcEnd"><span class="mono">${a ? 'FIN' : 'TERMINA'}</span><b>${a ? when(a.ends_at) : when(new Date(new Date(s.next_start).getTime() + planned * 3600000).toISOString())}</b></button>
      </div>
      <button type="button" class="${a ? 'btn-secondary' : 'btn-primary'} fc-main" id="fcMain">${a ? 'Terminar ayuno' : 'Empezar ayuno ahora'}</button>
      <p class="fc-foot">${s.week.done ? `${s.week.done} ayuno${s.week.done === 1 ? '' : 's'} completo${s.week.done === 1 ? '' : 's'} esta semana · ` : ''}En ayuno: agua, café o té sin azúcar.</p>`;
    el.querySelector('#fcPlan').addEventListener('click', openPlans);
    el.querySelector('#fcHist').addEventListener('click', openHistory);
    el.querySelector('#fcStage').addEventListener('click', () => openBody());
    el.querySelector('#fcMain').addEventListener('click', () => (a ? endNow() : startNow()));
    const fix = el.querySelector('#fcFix');
    if (fix) fix.addEventListener('click', () => openTime('¿A qué hora terminó?', null, (iso) => endNow(iso)));
    el.querySelector('#fcStart').addEventListener('click', () => {
      if (a) openTime('¿A qué hora empezó?', a.started_at, (iso) => call(() => apiPatch(`api/fasting/${a.id}`, { start: iso })));
      else openPlans();
    });
    el.querySelector('#fcEnd').addEventListener('click', () => {
      if (a) openTime('¿A qué hora terminó?', null, (iso) => endNow(iso));
      else openPlans();
    });
    tick();
    timer = setInterval(tick, 30000);
  }

  function tick() {
    if (!el || !state || el.hidden) return;
    const a = state.active;
    const now = Date.now();
    const top = el.querySelector('#fcTop');
    if (!top) return;
    if (a) {
      const start = new Date(a.started_at).getTime();
      const elapsed = now - start;
      const plannedMs = a.planned_h * 3600000;
      top.textContent = 'Llevas';
      el.querySelector('#fcBig').textContent = clock(elapsed);
      el.querySelector('#fcSmall').textContent = elapsed >= plannedMs ? '¡Llegaste a tu plan!' : `te faltan ${span(plannedMs - elapsed)}`;
      const stageIdx = state.stages.reduce((acc, x, i) => (elapsed / 3600000 >= x.from_h ? i : acc), 0);
      const st = el.querySelector('#fcStageText');
      if (st) st.textContent = `Ahora: ${state.stages[stageIdx].title.toLowerCase()} (aprox.)`;
      const fill = el.querySelector('.fc-fill');
      const c = 2 * Math.PI * 94;
      fill.setAttribute('stroke-dasharray', `${(c * Math.min(1, elapsed / plannedMs)).toFixed(1)} ${c.toFixed(1)}`);
      el.classList.toggle('reached', elapsed >= plannedMs);
    } else {
      const next = new Date(state.next_start).getTime();
      top.textContent = 'Tu ayuno empieza a las';
      el.querySelector('#fcBig').textContent = hhmm(new Date(next));
      el.querySelector('#fcSmall').textContent = `en ${span(next - now)}`;
      const windowMs = (24 - state.plan.hours) * 3600000;
      const fill = el.querySelector('.fc-fill');
      const c = 2 * Math.PI * 94;
      fill.setAttribute('stroke-dasharray', `${(c * Math.max(0, Math.min(1, 1 - (next - now) / windowMs))).toFixed(1)} ${c.toFixed(1)}`);
    }
  }

  async function mount(target, options) {
    el = target;
    opts = options || {};
    if (!el) return;
    if (!opts.today) { el.hidden = true; clearInterval(timer); return; }
    try {
      await apiGetSWR('api/fasting', (data) => { state = data; paint(); });
      if (opts.mealJustSaved && state && state.active && !state.blocked) askEndAfterMeal();
    } catch { el.hidden = true; } // the day still works without its fasting card
  }

  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.cadenceFasting = { mount, openIntro, openPlans, openBody };
})();
