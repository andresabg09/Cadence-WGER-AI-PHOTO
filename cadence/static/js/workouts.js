// Workouts: search an activity, pick a duration, log it (or edit / delete a logged one).
// The burn is an ESTIMATE (MET x your weight x hours) computed by the server; it never changes the day's goal.
(function () {
  const { icon, esc } = window.bits;
  const GROUP_COLOR = { caminar: '#E8C5D0', correr: '#A8E0D8', bici: '#C9D8FF', agua: '#BFE3FF', fuerza: '#FFD9B8', flexibilidad: '#E8D9FF', deporte: '#FFE6A8', otros: '#D8D8E4' };
  const DURATIONS = [15, 30, 60];
  let cache = null;

  const plain = (t) => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  async function load() {
    if (cache) return cache;
    cache = await apiGet('api/activities');
    cache.byKey = Object.fromEntries(cache.activities.map((a) => [a.key, a]));
    return cache;
  }

  function art(activity, size = 50) {
    const color = GROUP_COLOR[activity ? activity.group : 'otros'] || GROUP_COLOR.otros;
    return `<span class="wo-art" style="width:${size}px;height:${size}px;background:${color};">${icon(activity ? activity.icon : 'bolt', Math.round(size * 0.5), '#1B2540')}</span>`;
  }

  function layer(html, top) {
    const scrim = document.createElement('div');
    scrim.className = `sheet-scrim${top ? ' top' : ''}`;
    const sheet = document.createElement('div');
    sheet.className = `entry-sheet wo-sheet${top ? ' top' : ''}`;
    sheet.setAttribute('role', 'dialog');
    sheet.innerHTML = html;
    document.body.append(scrim, sheet);
    pushOverlay(() => { scrim.remove(); sheet.remove(); });
    scrim.addEventListener('click', () => dismissOverlay());
    return sheet;
  }

  const nowClock = () => { const d = new Date(); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };

  // The detail view. `workout` set = editing a logged one.
  function openDetail(activity, ctx, { day, workout, done, nested }) {
    let minutes = workout ? workout.minutes : 30;
    let custom = !DURATIONS.includes(minutes);
    const sheet = layer(`
      <div style="display:flex;justify-content:space-between;align-items:center;"><button type="button" class="icon-btn" id="woX" aria-label="Cerrar">${icon('x', 18)}</button>
        <input class="wo-time mono" id="woAt" type="time" value="${esc(workout && workout.at ? workout.at : nowClock())}" aria-label="Hora"></div>
      <div style="display:flex;flex-direction:column;align-items:center;gap:8px;margin-top:6px;">${art(activity, 84)}
        <h3 class="disp" style="font-size:22px;text-align:center;margin:0;">${esc(activity.label)}</h3>
        <div style="display:flex;align-items:center;gap:8px;font-size:14px;color:var(--ink-soft);"><span style="color:var(--ember);">${icon('flame', 17)}</span>
          <b class="mono" id="woKcal" style="color:var(--ink);"></b><span>kcal</span><span>·</span><span class="mono">${String(activity.kcal_per_min).replace('.', ',')} kcal / min</span></div>
        <div style="font-size:11.5px;color:var(--ink-soft);text-align:center;line-height:1.5;">Estimación con ${cache.weight_known ? `tu peso (${Math.round(cache.weight_kg)} kg)` : 'un peso de 70 kg: registra el tuyo en Perfil para afinarla'} y el esfuerzo de la actividad. No cambia tu meta del día.</div></div>
      <div class="wo-chips" id="woChips" role="group" aria-label="Duración"></div>
      <div id="woCustom" style="display:none;"><label class="field"><span>MINUTOS</span><div class="input-unit"><input class="input" id="woMin" type="number" inputmode="numeric" min="5" max="600" step="5" value="${minutes}"><i>min</i></div></label></div>
      <label class="field"><span>NOTA (OPCIONAL)</span><input class="input" id="woNote" maxlength="80" placeholder="Ej.: pecho y tríceps" value="${esc(workout && workout.note ? workout.note : '')}" autocomplete="off"></label>
      <div class="form-error" id="woErr" style="margin-top:10px;"></div>
      <div class="sheet-actions">${workout ? '<button type="button" class="btn-danger" id="woDel">Borrar</button>' : ''}<button type="button" class="btn-primary" id="woSave">${workout ? 'Guardar cambios' : '✓ Registrar entrenamiento'}</button></div>`, nested);
    const $ = (id) => sheet.querySelector(`#${id}`);
    const paint = () => {
      $('woKcal').textContent = Math.round(activity.kcal_per_min * (minutes || 0));
      $('woChips').innerHTML = [...DURATIONS.map((m) => [m, `${m} min`]), [0, 'Otro']].map(([m, label]) =>
        `<button type="button" data-m="${m}" aria-pressed="${m === 0 ? custom : (!custom && minutes === m)}">${label}</button>`).join('');
      $('woCustom').style.display = custom ? 'block' : 'none';
      $('woChips').querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
        const m = Number(b.dataset.m);
        if (m === 0) { custom = true; minutes = Number($('woMin').value) || 45; $('woMin').value = minutes; } else { custom = false; minutes = m; }
        if (window.sfx) sfx.play('pick');
        paint();
      }));
    };
    paint();
    $('woMin').addEventListener('input', () => { minutes = Number($('woMin').value) || 0; $('woKcal').textContent = Math.round(activity.kcal_per_min * minutes); });
    $('woX').addEventListener('click', () => dismissOverlay());
    const finish = () => (nested ? dismissOverlay(() => dismissOverlay(done)) : dismissOverlay(done));
    $('woSave').addEventListener('click', async () => {
      const err = $('woErr');
      err.classList.remove('show');
      const body = { kind: activity.key, minutes, note: $('woNote').value.trim() || null, at: $('woAt').value || null };
      try {
        if (workout) await apiPatch(`api/workouts/${workout.id}`, body);
        else await apiPost('api/workouts', { ...body, day });
        if (window.sfx) sfx.play('save');
        finish();
      } catch (e) { err.textContent = e.message || 'No se pudo guardar'; err.classList.add('show'); }
    });
    const del = $('woDel');
    if (del) del.addEventListener('click', async () => {
      try { await apiDelete(`api/workouts/${workout.id}`); if (window.sfx) sfx.play('remove'); finish(); } catch (e) { $('woErr').textContent = e.message; $('woErr').classList.add('show'); }
    });
  }

  async function openSearch(day, done) {
    try { await load(); } catch (err) { showToast(err.message || 'No se pudo cargar la lista'); return; }
    const sheet = layer(`
      <div style="display:flex;justify-content:space-between;align-items:center;"><button type="button" class="icon-btn" id="woClose" aria-label="Cerrar">${icon('x', 18)}</button></div>
      <h3 class="disp" style="font-size:24px;margin:12px 0;">Buscar entrenamiento</h3>
      <label class="wo-search"><span aria-hidden="true">${icon('search', 18)}</span><input id="woQ" type="search" placeholder="Correr, bicicleta, yoga…" autocomplete="off" aria-label="Buscar entrenamiento"></label>
      <div class="wo-list" id="woList"></div>`);
    const list = sheet.querySelector('#woList');
    const q = sheet.querySelector('#woQ');
    const draw = () => {
      const words = plain(q.value).split(/\s+/).filter(Boolean);
      const found = cache.activities.filter((a) => words.every((w) => plain(`${a.label} ${a.words} ${a.group}`).includes(w)));
      list.innerHTML = found.length ? found.map((a) => `<button type="button" class="wo-item" data-k="${a.key}">${art(a)}<span style="flex:1;text-align:left;">${esc(a.label)}</span><span class="mono" style="font-size:11px;color:var(--ink-soft);">${String(a.kcal_per_min).replace('.', ',')} kcal/min</span></button>`).join('')
        : '<p style="color:var(--ink-soft);font-size:13px;text-align:center;margin:24px 0;">No encontramos esa actividad. Prueba con otra palabra o elige «Otro».</p>';
      list.querySelectorAll('.wo-item').forEach((b) => b.addEventListener('click', () => { if (window.sfx) sfx.play('pick'); openDetail(cache.byKey[b.dataset.k], cache, { day, done, nested: true }); }));
    };
    q.addEventListener('input', draw);
    draw();
    sheet.querySelector('#woClose').addEventListener('click', () => dismissOverlay());
  }

  async function openEdit(workout, done) {
    try { await load(); } catch (err) { showToast(err.message); return; }
    openDetail(cache.byKey[workout.kind] || cache.byKey.otro, cache, { workout, done, nested: false });
  }

  window.cadenceWorkouts = { load, openSearch, openEdit, info: (kind) => (cache && cache.byKey[kind]) || null, art };
})();
