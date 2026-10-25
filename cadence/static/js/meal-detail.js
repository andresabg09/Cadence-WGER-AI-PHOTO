// Meal detail sheet: what you ate, its nutrition score, protein and fibre levels, awards, and how the score is made.
// Everything shown here comes from the server (/api/today): scores are fixed formulas over wger's values, never AI.
(function () {
  const { icon, segBar, hex, esc } = window.bits;
  function close(after) { dismissOverlay(after); }

  function layer(html, top) {
    const scrim = document.createElement('div');
    scrim.className = `sheet-scrim${top ? ' top' : ''}`;
    const sheet = document.createElement('div');
    sheet.className = `entry-sheet${top ? ' top' : ''}`;
    sheet.setAttribute('role', 'dialog');
    sheet.innerHTML = html;
    document.body.append(scrim, sheet);
    pushOverlay(() => { scrim.remove(); sheet.remove(); });
    scrim.addEventListener('click', () => close());
    return sheet;
  }

  function levelBlock(title, level, kind, targetText, emptyText) {
    if (!level) {
      return `<div class="md-card"><div class="md-label">${title}</div><div class="md-big disp" style="font-size:17px;color:var(--ink-soft);">Sin datos</div><div style="font-size:12px;color:var(--ink-soft);margin-top:6px;line-height:1.5;">${emptyText}</div></div>`;
    }
    const word = { bajo: 'bajo', medio: 'medio', alto: 'alto' }[level.label];
    return `<div class="md-card"><div class="md-label">${title}</div><div class="md-big disp">Nivel ${word}</div>${segBar(level.pct, `${Math.round(level.value_g)} g`)}
      <div style="font-size:12px;color:var(--ink-soft);line-height:1.5;">${targetText}</div></div>`;
  }

  function openFormula(score) {
    const parts = score.parts.map((p) => `<div class="part-row"><div class="top"><span>${esc(p.label)}</span><span class="mono" style="font-size:12px;">${p.points}<span style="color:var(--ink-soft);font-weight:600;"> / ${p.max}</span></span></div>
      <div class="bar"><i style="width:${(p.points / p.max * 100).toFixed(0)}%"></i></div><div class="note">${esc(p.note)}</div></div>`).join('');
    const sheet = layer(`
      <div class="md-head"><div><h3 class="disp" style="font-size:19px;">Cómo se calcula</h3><div style="font-size:12px;color:var(--ink-soft);margin-top:3px;">Siempre con los valores de wger, nunca con IA.</div></div>
        <div class="mono c-${score.label}" style="width:58px;height:58px;border-radius:50%;border:3px solid currentColor;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;flex-shrink:0;">${score.points}</div></div>
      ${parts}
      <div class="partial-note" style="margin-top:16px;"><span>${score.partial.length ? `Faltan datos de: ${esc(score.partial.join('; '))}. Esos criterios no restan: la puntuación se reparte entre los que sí tenemos.` : 'Tenemos todos los datos de este plato.'}</span></div>
      <div class="sheet-actions"><button class="btn-primary" id="mdOk">Entendido</button></div>`, true);
    sheet.querySelector('#mdOk').addEventListener('click', () => close());
  }

  function timeOf(meal) {
    const first = meal.items.map((i) => i.taken_at).filter(Boolean).sort()[0];
    return first ? new Date(first).toLocaleTimeString('es', { hour: 'numeric', minute: '2-digit' }) : '';
  }

  function openMealDetail(meal, day) {
    const share = { desayuno: 25, almuerzo: 35, merienda: 10, cena: 30, otro: 10 }[meal.key] || 10;
    const rows = meal.items.map((it) => `<div style="display:flex;align-items:center;gap:12px;"><div style="flex:1;min-width:0;"><div style="font-size:13.5px;font-weight:700;">${esc(it.name)}</div><div style="font-size:11.5px;color:var(--ink-soft);margin-top:2px;">${cadenceUnits.fmtAmount(it.amount_grams, it.liquid)}</div></div><div class="mono" style="font-size:12.5px;font-weight:700;">${Math.round(it.kcal)} <span style="color:var(--ink-soft);font-weight:600;font-size:10px;">KCAL</span></div></div>`).join('');
    const score = meal.score;
    const awards = (meal.awards || []).map((a) => `<div class="hex-cell">${bits.award(a.art, 58)}<span>${esc(a.title)}</span></div>`).join('');
    const sheet = layer(`
      <div class="md-head"><div><h3 class="disp" style="font-size:19px;">${esc(meal.label)}</h3><div class="when">${day && day.date === day.today ? 'Hoy' : esc(day ? day.date : '')}${timeOf(meal) ? ` · ${timeOf(meal)}` : ''}</div></div>
        <button type="button" id="mdClose" class="icon-btn" aria-label="Cerrar">${icon('x', 18)}</button></div>
      <div class="md-card" style="display:flex;flex-direction:column;gap:12px;margin-top:14px;">${rows}
        <div style="height:1px;background:var(--card-border);"></div>
        <div style="display:flex;justify-content:space-between;font-size:12.5px;"><span style="color:var(--ink-soft);font-weight:600;">Total</span><span class="mono" style="font-weight:700;">${Math.round(meal.totals.kcal)} kcal</span></div></div>
      ${score ? `<div class="md-card"><div class="md-head"><div><div class="md-label">PUNTUACIÓN NUTRICIONAL</div><div class="md-big disp c-${score.label}">${score.label}</div></div>
        <button type="button" class="chip-btn" id="mdHow">¿Cómo se calcula?</button></div>${segBar(score.points, String(score.points))}
        ${awards ? `<div class="md-label">PREMIOS DE ESTE PLATO · ${(meal.awards || []).length}</div><div class="hex-row">${awards}</div>` : ''}</div>` : ''}
      ${levelBlock('PROTEÍNA', meal.levels && meal.levels.protein, 'protein', meal.levels && meal.levels.protein ? `Tu parte sugerida para esta comida es de unos ${Math.round(meal.levels.protein.target_g)} g (el ${share} % de tu meta diaria).` : '', '')}
      ${levelBlock('FIBRA', meal.levels && meal.levels.fibre, 'fibre', meal.levels && meal.levels.fibre ? `Sugerido para esta comida: unos ${Math.round(meal.levels.fibre.target_g)} g.` : '', 'Faltan datos de fibra en esta comida, así que no podemos decir si es poca o mucha.')}
      ${score && score.partial.length ? `<div class="partial-note" style="margin-top:12px;"><span><strong style="color:var(--ink);">Datos parciales.</strong> Faltan: ${esc(score.partial.join('; '))}. No restan puntos: solo cuenta lo que sí tenemos.</span></div>` : ''}
      <p style="margin:14px 0 0;font-size:11px;color:var(--ink-soft);line-height:1.5;text-align:center;">Puntuación orientativa calculada con los valores de wger. No es consejo médico.</p>`);
    sheet.querySelector('#mdClose').addEventListener('click', () => close());
    const how = sheet.querySelector('#mdHow');
    if (how) how.addEventListener('click', () => openFormula(score));
  }

  window.openMealDetail = openMealDetail;
})();
