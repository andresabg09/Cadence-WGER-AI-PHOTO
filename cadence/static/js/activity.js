// "Tu día a día": the AI interview (chat or voice) and, always one tap away, the same answers as options.
// The AI only listens and fills these answers in; the person sees and corrects them, and the server does the maths.
(function () {
  const esc = (s) => escapeHtml(String(s == null ? '' : s));
  let OPTIONS = null;
  async function options() { if (!OPTIONS) OPTIONS = await apiGet('api/lifestyle'); return OPTIONS; }
  const GROUP_NAMES = { caminar: 'Caminar', correr: 'Correr', bici: 'Bicicleta', agua: 'Agua', fuerza: 'Fuerza y gimnasio', flexibilidad: 'Flexibilidad', deporte: 'Deportes y baile', otros: 'Otros' };
  const STRENGTH = new Set(['pesas', 'pesas_fuertes', 'calistenia']);
  const MIC = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M5 11a7 7 0 0014 0M12 18v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>';
  const LIFT = [['beginner', 'Menos de 1 año', 'O todavía no entreno fuerza.'], ['intermediate', '1 a 3 años', 'Entreno con constancia.'], ['advanced', 'Más de 3 años', 'Con progresión sostenida.']];

  // box: where to draw. opts: { goal, value (saved answers), onChange(read), startWith: 'chat' | 'form' }
  async function mount(box, opts = {}) {
    const lists = await options().catch(() => ({ levels: [], activities: [] }));
    const state = {
      lifestyle: opts.value && opts.value.lifestyle || null,
      steps: opts.value && opts.value.steps != null ? String(opts.value.steps) : '',
      training: ((opts.value && opts.value.training) || []).map((t) => ({ kind: t.kind, minutes: t.minutes, days: t.days })),
      lift_exp: opts.value && opts.value.lift_exp || null,
      body_fat_pct: opts.value && opts.value.body_fat_pct != null ? String(opts.value.body_fat_pct) : '',
    };
    let none = Boolean(opts.value && opts.value.lifestyle && !state.training.length); // said "no planned exercise"
    let understood = null;
    let mode = opts.startWith === 'form' || !opts.chat ? 'form' : 'chat';
    let history = [];
    let busy = false;
    let dict = null;       // the dictation on the message box
    let chatOffline = false;

    const level = () => (state.steps !== '' && Number(state.steps) >= 0 ? stepsLevel(Number(state.steps)) : state.lifestyle);
    const stepsLevel = (n) => (n < 4000 ? 'very_low' : n < 7000 ? 'low' : n < 10000 ? 'light' : n < 12500 ? 'moderate' : 'heavy');
    const levelInfo = (key) => lists.levels.find((l) => l.key === key);
    const goal = () => (typeof opts.goal === 'function' ? opts.goal() : opts.goal);
    // Experience is asked ONLY of someone who really lifts: no exercise, no question about training years.
    const wantsLift = () => !none && state.training.some((t) => STRENGTH.has(t.kind));
    const wantsMuscle = () => goal() === 'muscle' || goal() === 'gain';

    function read() {
      const training = none ? [] : state.training.filter((t) => t.kind && Number(t.minutes) >= 5 && Number(t.days) > 0)
        .map((t) => ({ kind: t.kind, minutes: Math.round(Number(t.minutes)), days: Number(t.days) }));
      const steps = state.steps !== '' && Number.isFinite(Number(state.steps)) ? Math.round(Number(state.steps)) : null;
      return {
        lifestyle: level(), steps, training,
        lift_exp: wantsLift() ? state.lift_exp : null, // ask-only-if-they-lift; the server treats a muscle goal without it as a beginner
        body_fat_pct: state.body_fat_pct !== '' && Number(state.body_fat_pct) >= 3 ? Number(state.body_fat_pct) : null,
      };
    }
    function problem() {
      if (mode === 'chat') return 'Cuéntame tu día a día, o toca “Prefiero responder con opciones”.';
      if (!level()) return 'Elige cómo es tu día a día.';
      if (state.steps !== '' && !(Number(state.steps) >= 0 && Number(state.steps) <= 40000)) return 'Revisa tus pasos (entre 0 y 40.000).';
      if (!none && state.training.length && state.training.some((t) => !(Number(t.minutes) >= 5 && Number(t.minutes) <= 240 && Number(t.days) >= 0.5 && Number(t.days) <= 7))) return 'Revisa tu ejercicio: de 5 a 240 minutos y de 1 a 7 días por semana.';
      if (!none && !state.training.length) return 'Agrega tu ejercicio o toca “No hago ejercicio planificado”.';
      if (wantsLift() && !state.lift_exp) return 'Cuéntanos cuánto llevas entrenando fuerza.';
      return '';
    }
    const changed = () => { if (opts.onChange) opts.onChange(read()); };

    // ------------------------------------------------------------ chat
    function bubble(role, text, voice) {
      const m = box.querySelector('.ac-msgs');
      if (!m) return;
      const el = document.createElement('div');
      el.className = `ac-msg ${role}${voice ? ' voice' : ''}`;
      el.textContent = text;
      m.append(el);
      m.scrollTop = m.scrollHeight;
    }
    function typing(on) {
      const m = box.querySelector('.ac-msgs');
      if (!m) return;
      m.querySelectorAll('.ac-typing').forEach((n) => n.remove());
      if (on) { const t = document.createElement('div'); t.className = 'ac-typing'; t.innerHTML = '<i></i><i></i><i></i>'; m.append(t); m.scrollTop = m.scrollHeight; }
    }
    function lock(on) {
      busy = on;
      box.querySelectorAll('.ac-compose textarea, #acSend').forEach((n) => { n.disabled = on; });
    }
    function toForm(reason) {
      mode = 'form';
      if (reason) understood = reason;
      draw();
      changed();
    }
    function handleTurn(out) {
      typing(false);
      if (out.reply) { bubble('bot', out.reply); history.push({ role: 'assistant', text: out.reply }); }
      if (out.fallback) { setTimeout(() => toForm(null), 900); return; }
      if (out.done && out.activity) {
        const a = out.activity;
        state.lifestyle = a.lifestyle; state.steps = a.steps != null ? String(a.steps) : '';
        state.training = (a.training || []).map((t) => ({ kind: t.kind, minutes: t.minutes, days: t.days }));
        none = !state.training.length;
        state.lift_exp = a.lift_exp || state.lift_exp;
        if (window.sfx) sfx.play('pick');
        setTimeout(() => toForm(a.summary || []), 1100);
      }
    }
    async function turn(promise) {
      lock(true); typing(true);
      try { handleTurn(await promise); }
      catch (err) {
        typing(false);
        chatOffline = true;
        bubble('bot', `${err.message || 'No pude hablar con la IA ahora.'} Puedes responder con las opciones.`);
        setTimeout(() => toForm(null), 1400);
      }
      lock(false);
      const f = box.querySelector('#acText');
      if (f && mode === 'chat') f.focus();
    }
    function send() {
      const field = box.querySelector('#acText');
      if (!field || busy) return;
      if (dict) dict.stop();   // sending ends the listening; what was written is exactly what goes
      const t = field.value.trim();
      if (!t) return;
      bubble('me', t);
      history.push({ role: 'user', text: t });
      field.value = ''; cadenceDictation.grow(field);
      turn(apiPost('api/interview', { history, goal: goal() || null }));
    }

    function drawChat() {
      if (dict) { dict.stop(); dict = null; }
      box.innerHTML = `<div class="ac">
        <div class="ac-msgs" aria-live="polite"></div>
        <div class="ac-compose">
          <button type="button" class="ac-round" id="acMic" aria-label="Dictar con la voz" aria-pressed="false">${MIC}</button>
          <textarea class="input ac-text" id="acText" rows="1" data-placeholder="Escribe o dicta…" placeholder="Escribe o dicta…" autocomplete="off" maxlength="1400" enterkeyhint="send"></textarea>
          <button type="button" class="ac-round go" id="acSend" aria-label="Enviar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        </div>
        <p class="ac-hint ac-voice" id="acHint">Toca el micrófono y habla: tu voz se escribe aquí. Léelo, corrígelo y envíalo cuando quieras.</p>
        <button type="button" class="ac-ask" id="acForm">Prefiero responder con opciones</button>
      </div>`;
      const field = box.querySelector('#acText');
      const hint = box.querySelector('#acHint');
      const calm = hint.textContent;
      dict = cadenceDictation.attach({ field, button: box.querySelector('#acMic'), onHint: (t) => { hint.textContent = t || calm; }, onError: (t) => { hint.textContent = t; } });
      box.querySelector('#acSend').addEventListener('click', send);
      field.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
      box.querySelector('#acForm').addEventListener('click', () => { if (dict) dict.stop(); toForm(null); });
      if (!history.length) turn(apiPost('api/interview', { history: [], goal: goal() || null }));
      else history.forEach((m) => bubble(m.role === 'assistant' ? 'bot' : 'me', m.text));
    }

    // ------------------------------------------------------------ the options form
    function rowHtml(t, i) {
      const groups = {};
      lists.activities.forEach((a) => { (groups[a.group] = groups[a.group] || []).push(a); });
      const sel = Object.entries(groups).map(([g, items]) => `<optgroup label="${esc(GROUP_NAMES[g] || g)}">${items.map((a) => `<option value="${esc(a.key)}" ${a.key === t.kind ? 'selected' : ''}>${esc(a.label)}</option>`).join('')}</optgroup>`).join('');
      return `<div class="ac-row" data-i="${i}"><select class="input" data-f="kind" aria-label="Ejercicio">${sel}</select>
        <input class="input" data-f="minutes" type="number" inputmode="numeric" min="5" max="240" placeholder="min" value="${esc(t.minutes)}" aria-label="Minutos por sesión">
        <input class="input" data-f="days" type="number" inputmode="decimal" min="0.5" max="7" step="0.5" placeholder="días" value="${esc(t.days)}" aria-label="Días por semana">
        <button type="button" class="ac-x" data-del="${i}" aria-label="Quitar"><i data-ico="x"></i></button></div>`;
    }
    function drawForm() {
      const lv = level();
      const info = lv && levelInfo(lv);
      const fat = state.body_fat_pct !== '';
      box.innerHTML = `<div class="ac">
        ${understood && understood.length ? `<div class="ac-heard"><b>Esto entendí de lo que me contaste</b>Revísalo y corrige lo que no sea así.<ul>${understood.map((l) => `<li>${esc(l)}</li>`).join('')}</ul></div>` : ''}
        <div class="ac-sec">TU DÍA A DÍA, SIN CONTAR EL EJERCICIO</div>
        <div class="choice-grid" id="acLevels">${lists.levels.map((l) => `<button type="button" class="choice" data-level="${l.key}" aria-pressed="${state.steps === '' && state.lifestyle === l.key}"><div class="ac-level"><b>${esc(l.title)}</b><small>${esc(l.text)}</small><small class="steps">${esc(l.steps)}</small></div></button>`).join('')}</div>
        <label class="field" style="margin:0;"><span>¿SABES TUS PASOS? (OPCIONAL)</span><div class="input-unit"><input class="input" id="acSteps" type="number" inputmode="numeric" min="0" max="40000" placeholder="Ej. 6000" value="${esc(state.steps)}"><i>pasos</i></div></label>
        <p class="ac-hint">${state.steps !== '' && info ? `Con tus pasos: <b>${esc(info.title.toLowerCase())}</b>. ` : ''}Míralos en Salud (iPhone) o Google Fit: un día normal, sin entrenar. Si los escribes, mandan sobre lo que elegiste arriba.</p>
        <div class="ac-sec">EJERCICIO PLANIFICADO</div>
        <div class="ac-switch"><button type="button" id="acNone" aria-pressed="${none}">No hago ejercicio planificado</button><button type="button" id="acSome" aria-pressed="${!none}">Sí hago</button></div>
        ${none ? '' : `<div class="ac-row-head"><span>EJERCICIO</span><span>MIN</span><span>DÍAS/SEM</span><span></span></div>
        ${state.training.map(rowHtml).join('')}
        ${state.training.length < 4 ? '<button type="button" class="ac-ask dashed" id="acAdd">Agregar otro ejercicio</button>' : ''}
        <p class="ac-hint">Cuenta solo lo que haces con regularidad y los minutos que de verdad te mueves. Caminar al trabajo o las tareas de casa ya cuentan en tu día a día.</p>`}
        ${wantsMuscle() && !wantsLift() ? `<p class="ac-hint" style="background:rgba(124,92,255,0.10);border:1px solid rgba(124,92,255,0.3);border-radius:14px;padding:12px 14px;">Para ganar músculo hace falta entrenar fuerza (cada músculo al menos 2 veces por semana). Mientras no entrenes, calculamos tu meta como si empezaras desde cero.</p>` : ''}
        ${wantsLift() ? `<div class="ac-sec">¿CUÁNTO LLEVAS ENTRENANDO FUERZA?</div><div class="choice-grid">${LIFT.map(([k, t, s]) => `<button type="button" class="choice" data-lift="${k}" aria-pressed="${state.lift_exp === k}"><b>${t}</b><small>${s}</small></button>`).join('')}</div>` : ''}
        <details ${fat ? 'open' : ''}><summary class="ac-hint" style="cursor:pointer;">Conozco mi porcentaje de grasa corporal (opcional)</summary>
          <label class="field" style="margin:10px 0 0;"><span>GRASA CORPORAL</span><div class="input-unit"><input class="input" id="acFat" type="number" inputmode="decimal" min="3" max="60" step="0.5" placeholder="Ej. 22" value="${esc(state.body_fat_pct)}"><i>%</i></div></label>
          <p class="ac-hint" style="margin-top:6px;">De una báscula con bioimpedancia, plicómetro o DEXA. Hace el cálculo más exacto.</p></details>
        ${opts.chat && !chatOffline ? '<button type="button" class="ac-ask" id="acChat">Mejor lo hablo con la IA</button>' : ''}
      </div>`;
      box.querySelectorAll('[data-level]').forEach((b) => b.addEventListener('click', () => { state.lifestyle = b.dataset.level; state.steps = ''; if (window.sfx) sfx.play('pick'); draw(); changed(); }));
      // A field's own change event fires while it loses focus: drawing right then removes it mid-blur (Chrome throws), so draw a tick later.
      box.querySelector('#acSteps').addEventListener('change', (e) => { state.steps = e.target.value.trim(); if (state.steps !== '') state.lifestyle = stepsLevel(Number(state.steps)); changed(); setTimeout(draw, 0); });
      box.querySelector('#acNone').addEventListener('click', () => { none = true; if (window.sfx) sfx.play('pick'); draw(); changed(); });
      box.querySelector('#acSome').addEventListener('click', () => { none = false; if (!state.training.length) state.training.push({ kind: 'caminar', minutes: 30, days: 3 }); if (window.sfx) sfx.play('pick'); draw(); changed(); });
      const add = box.querySelector('#acAdd');
      if (add) add.addEventListener('click', () => { state.training.push({ kind: 'pesas', minutes: 45, days: 3 }); draw(); changed(); });
      box.querySelectorAll('.ac-row').forEach((row) => {
        const i = Number(row.dataset.i);
        row.querySelectorAll('[data-f]').forEach((el) => el.addEventListener('change', () => {
          state.training[i][el.dataset.f] = el.dataset.f === 'kind' ? el.value : el.value === '' ? '' : Number(el.value);
          changed();
          if (el.dataset.f === 'kind') setTimeout(draw, 0);
        }));
      });
      box.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', () => { state.training.splice(Number(b.dataset.del), 1); if (!state.training.length) none = true; draw(); changed(); }));
      box.querySelectorAll('[data-lift]').forEach((b) => b.addEventListener('click', () => { state.lift_exp = b.dataset.lift; if (window.sfx) sfx.play('pick'); draw(); changed(); }));
      box.querySelector('#acFat').addEventListener('change', (e) => { state.body_fat_pct = e.target.value.trim(); changed(); });
      const chat = box.querySelector('#acChat');
      if (chat) chat.addEventListener('click', () => { mode = 'chat'; understood = null; history = []; draw(); changed(); });
    }

    function draw() { if (mode === 'chat') drawChat(); else drawForm(); }
    draw();
    changed();
    return { read, problem, inChat: () => mode === 'chat', toForm: () => toForm(null) };
  }

  window.cadenceActivity = { mount };
})();
