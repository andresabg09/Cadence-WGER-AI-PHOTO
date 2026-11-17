// "Rápido" (17 nov 2026): register without a photo, in a few taps.
//   cadenceQuickLog.open({ meal })       - Básicos (home measures) | Solo calorías (the kcal you already know)
//   cadenceQuickLog.openLabel({ meal })  - a photo of a product's nutrition table -> the food sheet, filled in, to check
// The calories of a basic come from the catalog; "Solo calorías" are typed by the person; a label is only transcribed by
// the AI and the person checks every number before saving. Every sheet closes with the system Back button.
(function () {
  const MEALS = [['desayuno', 'Desayuno'], ['almuerzo', 'Almuerzo'], ['merienda', 'Merienda'], ['cena', 'Cena']];
  const ic = (n) => (window.cadenceIcons ? cadenceIcons.icon(n) : '');
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const mealNow = () => { const h = new Date().getHours(); return h < 11 ? 'desayuno' : h < 15 ? 'almuerzo' : h < 18 ? 'merienda' : 'cena'; };
  const mealName = (k) => (MEALS.find(([key]) => key === k) || [k, k])[1].toLowerCase();

  // The pages that open "Rápido" do not all load these: fetch what is missing, once.
  function need(src, ready) {
    if (ready()) return Promise.resolve();
    return new Promise((ok) => { const t = document.createElement('script'); t.src = src; t.onload = ok; t.onerror = ok; document.head.appendChild(t); });
  }
  const needAll = () => need('static/js/units.js', () => window.cadenceUnits)
    .then(() => need('static/js/portions.js', () => window.cadencePortions))
    .then(() => need('static/js/food-sheet.js', () => typeof window.openFoodSheet === 'function'));

  function sheet(html, bind) {
    const scrim = document.createElement('div');
    scrim.className = 'sheet-scrim';
    const box = document.createElement('div');
    box.className = 'entry-sheet quick-sheet';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.innerHTML = html;
    document.body.append(scrim, box);
    pushOverlay(() => { scrim.remove(); box.remove(); });
    scrim.addEventListener('click', () => dismissOverlay());
    box.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => dismissOverlay()));
    bind(box, (after) => dismissOverlay(after));
  }

  // Saved: on Hoy the day reloads (and celebrates, and asks about an open fast); elsewhere we go to Hoy.
  function done(result, meal) {
    const day = result && result.date;
    const text = `Guardado en ${mealName(meal)}`;
    if (window.sfx) sfx.play('save');
    try {
      sessionStorage.setItem('cadence_flash', text);
      sessionStorage.setItem('cadence_flash_kind', 'ok');
      if (day) sessionStorage.setItem('cadence_open_date', day);
    } catch { /* no storage: the toast below still says it */ }
    if (window.swrClear) swrClear();
    if (typeof window.applyReturnHints === 'function' && typeof window.loadToday === 'function') { window.applyReturnHints(); window.loadToday(); return; }
    window.location.href = 'index.html';
  }

  const mealChips = (current) => `<div class="chips qk-meals" role="radiogroup" aria-label="Comida">${MEALS.map(([k, l]) => `<button type="button" class="chip${k === current ? ' on' : ''}" role="radio" aria-checked="${k === current}" data-meal="${k}">${l}</button>`).join('')}</div>`;
  function wireMeals(box, set) {
    box.querySelectorAll('[data-meal]').forEach((b) => b.addEventListener('click', () => {
      set(b.dataset.meal);
      box.querySelectorAll('[data-meal]').forEach((x) => { x.classList.toggle('on', x === b); x.setAttribute('aria-checked', String(x === b)); });
      if (window.sfx) sfx.play('pick');
    }));
  }

  // How much of one food, in home measures (cup, unit, slice, spoon) or grams. Calories from the catalog value per 100 g.
  function amountPanel(food) {
    const names = [food.name];
    const measures = window.cadencePortions ? cadencePortions.measuresFor(names, food.liquid) : [];
    const list = measures.concat([{ key: 'g', one: food.liquid ? 'ml' : 'g', many: food.liquid ? 'ml' : 'g', g: 1 }]);
    const first = list[0];
    return { list, measure: first, qty: first.key === 'g' ? 100 : 1 };
  }

  function open(options) { needAll().then(() => openNow(options)); }
  function openNow(options) {
    const opts = options || {};
    let meal = opts.meal || mealNow();
    let tab = opts.tab || 'basics';
    let picked = null; // {food, list, measure, qty}
    sheet(`
      <div class="fs-head"><div><div class="fs-kick mono">REGISTRAR</div><h3 class="disp">Rápido</h3></div><button type="button" class="icon-btn" data-close aria-label="Cerrar">${ic('x')}</button></div>
      <div class="seg-toggle qk-tabs" role="tablist"><button type="button" role="tab" data-tab="basics">Básicos</button><button type="button" role="tab" data-tab="kcal">Solo calorías</button></div>
      ${mealChips(meal)}
      <div id="qkBody"></div>
      <div class="form-error" id="qkErr"></div>
      <div class="sheet-actions"><button type="button" class="btn-primary" id="qkSave">Agregar</button></div>`, (box, close) => {
      const body = box.querySelector('#qkBody');
      const save = box.querySelector('#qkSave');
      const err = (text) => { const e = box.querySelector('#qkErr'); e.textContent = text || ''; e.classList.toggle('show', !!text); };
      wireMeals(box, (m) => { meal = m; paintSave(); });

      function grams() { return picked ? picked.qty * picked.measure.g : 0; }
      function paintSave() {
        if (tab === 'kcal') {
          const k = Number((box.querySelector('#qkKcal') || {}).value || 0);
          save.textContent = k > 0 ? `Sumar ${Math.round(k)} kcal a${meal === 'almuerzo' ? 'l' : ' la'} ${mealName(meal)}` : 'Agregar';
          save.disabled = !(k > 0);
          return;
        }
        save.disabled = !picked;
        save.textContent = picked ? `Agregar a${meal === 'almuerzo' ? 'l' : ' la'} ${mealName(meal)}` : 'Elige un alimento';
      }
      function paintAmount() {
        const panel = body.querySelector('#qkAmount');
        if (!panel) return;
        if (!picked) { panel.hidden = true; return; }
        panel.hidden = false;
        const g = grams();
        const kcal = Math.round((picked.food.energy_kcal_100g || 0) * g / 100);
        const qtyText = picked.measure.key === 'g' ? `${Math.round(picked.qty)} ${picked.measure.one}` : cadencePortions.label(picked.measure, picked.qty);
        panel.innerHTML = `
          <div class="qk-amount-head"><b>${esc(picked.food.name)}</b><span class="mono">${kcal} kcal</span></div>
          <div class="chips">${picked.list.map((m, i) => `<button type="button" class="chip${m === picked.measure ? ' on' : ''}" data-m="${i}">${esc(m.key === 'g' ? m.one : m.one)}</button>`).join('')}</div>
          <div class="qk-step"><button type="button" class="step-btn" data-q="-1" aria-label="Menos">${ic('minus')}</button><span class="disp">${esc(qtyText)}</span><button type="button" class="step-btn" data-q="1" aria-label="Más">${ic('plus')}</button></div>
          <small class="qk-hint">${picked.measure.key === 'g' ? '' : `≈ ${Math.round(g)} ${picked.food.liquid ? 'ml' : 'g'} · `}calorías del catálogo de alimentos</small>`;
        panel.querySelectorAll('[data-m]').forEach((b) => b.addEventListener('click', () => {
          picked.measure = picked.list[Number(b.dataset.m)];
          picked.qty = picked.measure.key === 'g' ? 100 : 1;
          paintAmount();
        }));
        panel.querySelectorAll('[data-q]').forEach((b) => b.addEventListener('click', () => {
          const d = Number(b.dataset.q);
          picked.qty = picked.measure.key === 'g' ? Math.max(5, picked.qty + d * (picked.qty < 50 ? 5 : 25)) : cadencePortions.stepQty(picked.qty, d);
          paintAmount();
        }));
      }

      async function paintBasics() {
        body.innerHTML = '<p class="qk-hint" style="margin:6px 0 10px;">Toca un alimento y elige la medida de tu casa.</p><div class="qk-grid" id="qkGrid"><div class="skeleton" style="height:84px;"></div><div class="skeleton" style="height:84px;"></div><div class="skeleton" style="height:84px;"></div></div><div class="qk-amount" id="qkAmount" hidden></div><a class="qk-more" href="search.html?meal=' + encodeURIComponent(meal) + '">Buscar otro alimento</a>';
        try {
          await apiGetSWR('api/quick/basics', (foods) => {
            const grid = body.querySelector('#qkGrid');
            if (!grid) return;
            if (!foods.length) { grid.innerHTML = '<p class="qk-hint">Los básicos no están disponibles ahora. Usa "Buscar otro alimento".</p>'; return; }
            grid.innerHTML = foods.map((f, i) => `<button type="button" class="qk-food" data-f="${i}"><span class="qk-pic" data-food="${esc(f.name)}">${esc(f.name.slice(0, 1))}</span><span>${esc(f.name)}</span></button>`).join('');
            if (window.cadenceFoodPhoto) cadenceFoodPhoto.hydrate(grid);
            grid.querySelectorAll('[data-f]').forEach((b) => b.addEventListener('click', () => {
              const food = foods[Number(b.dataset.f)];
              picked = { food, ...amountPanel(food) };
              grid.querySelectorAll('.qk-food').forEach((x) => x.classList.toggle('on', x === b));
              if (window.sfx) sfx.play('pick');
              paintAmount();
              paintSave();
              body.querySelector('#qkAmount').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
            }));
          });
        } catch (e) { body.querySelector('#qkGrid').innerHTML = `<p class="qk-hint">${esc(e.message)}</p>`; }
      }
      function paintKcal() {
        body.innerHTML = `
          <p class="qk-hint" style="margin:6px 0 10px;">¿Ya sabes las calorías (de una etiqueta o un restaurante)? Anótalas tal cual: las escribes tú, nadie las adivina.</p>
          <label class="field"><span>QUÉ FUE (OPCIONAL)</span><input class="input" id="qkName" maxlength="60" placeholder="Almuerzo del trabajo" autocomplete="off"></label>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <label class="field"><span>CALORÍAS</span><div class="input-unit"><input class="input" id="qkKcal" type="number" inputmode="numeric" min="1" max="5000" step="1"><i>kcal</i></div></label>
            <label class="field"><span>PROTEÍNA (OPCIONAL)</span><div class="input-unit"><input class="input" id="qkProt" type="number" inputmode="numeric" min="0" max="300" step="1"><i>g</i></div></label>
          </div>
          <p class="qk-hint">Cuenta para tus calorías del día y tu racha. Sin alimentos, la puntuación de esa comida queda con datos parciales.</p>`;
        body.querySelector('#qkKcal').addEventListener('input', paintSave);
        setTimeout(() => body.querySelector('#qkKcal').focus(), 60);
      }
      function setTab(t) {
        tab = t;
        box.querySelectorAll('[data-tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
        err('');
        if (t === 'basics') paintBasics(); else paintKcal();
        paintSave();
      }
      box.querySelectorAll('[data-tab]').forEach((b) => b.addEventListener('click', () => setTab(b.dataset.tab)));

      save.addEventListener('click', async () => {
        err('');
        save.disabled = true;
        try {
          let result;
          if (tab === 'kcal') {
            const prot = box.querySelector('#qkProt').value;
            result = await apiPost('api/quick', { kcal: Number(box.querySelector('#qkKcal').value), protein: prot === '' ? null : Number(prot), name: box.querySelector('#qkName').value.trim() || null, meal });
          } else {
            result = await apiPost('api/confirm', { items: [{ ingredient_id: picked.food.id, amount_grams: Math.round(grams() * 10) / 10, liquid: !!picked.food.liquid }], meal });
          }
          close(() => done(result, meal));
        } catch (e) { err(e.message || 'No se pudo guardar'); save.disabled = false; }
      });
      setTab(tab);
    });
  }

  // ---------------------------------------------------------------- the label
  function shrink(file, max) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob((blob) => { URL.revokeObjectURL(img.src); resolve(blob || file); }, 'image/jpeg', 0.9);
      };
      img.onerror = () => resolve(file);
      img.src = URL.createObjectURL(file);
    });
  }

  // The photo must be picked inside the tap itself (browsers block a file chooser opened later), so this creates the input
  // and clicks it at once; the reading happens after the person chose the photo.
  function pickPhoto(onFile) {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.setAttribute('capture', 'environment');
    input.style.display = 'none';
    document.body.appendChild(input);
    input.addEventListener('change', () => { const file = input.files && input.files[0]; input.remove(); if (file) onFile(file); });
    input.click();
  }
  function openLabel(options) { pickPhoto((file) => readLabel(file, options)); }

  async function readLabel(file, options) {
    const meal = (options && options.meal) || mealNow();
    showToast('Leyendo la etiqueta…', 'warn');
    try {
      const form = new FormData();
      form.append('image', await shrink(file, 1800), 'etiqueta.jpg');
      const read = await apiPost('api/label', form, { isFormData: true });
      if (window.sfx) sfx.play('photo');
      await needAll();
      openFoodSheet({ name: read.name || '', kcal: read.kcal, protein: read.protein, carbs: read.carbs, fat: read.fat, fibre: read.fibre, liquid: read.liquid,
        notice: { title: 'Revisa la etiqueta', text: `La IA solo copió los números impresos${read.basis === 'serving' && read.serving.size ? ` (por porción de ${read.serving.size} ${read.serving.unit || 'g'}, ya pasados a 100 ${read.liquid ? 'ml' : 'g'})` : ''}. Compáralos con la etiqueta y corrige lo que haga falta: nada se guarda sin tu toque.` } },
      (food) => pickAmount(food, meal));
    } catch (e) {
      showToast(e.message || 'No se pudo leer la etiqueta');
    }
  }

  // After saving a food from a label: how much of it went into which meal.
  function pickAmount(food, meal) {
    let current = meal;
    const picked = { food: { ...food, liquid: !!food.liquid }, ...amountPanel({ ...food, liquid: !!food.liquid }) };
    sheet(`
      <div class="fs-head"><div><div class="fs-kick mono">CUÁNTO</div><h3 class="disp">${esc(food.name)}</h3></div><button type="button" class="icon-btn" data-close aria-label="Cerrar">${ic('x')}</button></div>
      ${mealChips(current)}
      <div class="qk-amount" id="qkAmount"></div>
      <div class="form-error" id="qkErr"></div>
      <div class="sheet-actions"><button type="button" class="btn-secondary" data-close>Solo guardarlo</button><button type="button" class="btn-primary" id="qkSave">Agregar</button></div>`, (box, close) => {
      wireMeals(box, (m) => { current = m; });
      const panel = box.querySelector('#qkAmount');
      const paint = () => {
        const g = picked.qty * picked.measure.g;
        const qtyText = picked.measure.key === 'g' ? `${Math.round(picked.qty)} ${picked.measure.one}` : cadencePortions.label(picked.measure, picked.qty);
        panel.innerHTML = `<div class="qk-amount-head"><b>${Math.round((food.energy_kcal_100g || 0) * g / 100)} kcal</b><span class="mono">≈ ${Math.round(g)} ${picked.food.liquid ? 'ml' : 'g'}</span></div>
          <div class="chips">${picked.list.map((m, i) => `<button type="button" class="chip${m === picked.measure ? ' on' : ''}" data-m="${i}">${esc(m.one)}</button>`).join('')}</div>
          <div class="qk-step"><button type="button" class="step-btn" data-q="-1" aria-label="Menos">${ic('minus')}</button><span class="disp">${esc(qtyText)}</span><button type="button" class="step-btn" data-q="1" aria-label="Más">${ic('plus')}</button></div>`;
        panel.querySelectorAll('[data-m]').forEach((b) => b.addEventListener('click', () => { picked.measure = picked.list[Number(b.dataset.m)]; picked.qty = picked.measure.key === 'g' ? 100 : 1; paint(); }));
        panel.querySelectorAll('[data-q]').forEach((b) => b.addEventListener('click', () => {
          const d = Number(b.dataset.q);
          picked.qty = picked.measure.key === 'g' ? Math.max(5, picked.qty + d * (picked.qty < 50 ? 5 : 25)) : cadencePortions.stepQty(picked.qty, d);
          paint();
        }));
      };
      paint();
      box.querySelector('#qkSave').addEventListener('click', async () => {
        try {
          const result = await apiPost('api/confirm', { items: [{ ingredient_id: food.id, amount_grams: Math.round(picked.qty * picked.measure.g * 10) / 10, liquid: picked.food.liquid }], meal: current });
          close(() => done(result, current));
        } catch (e) { const el = box.querySelector('#qkErr'); el.textContent = e.message; el.classList.add('show'); }
      });
    });
  }

  window.cadenceQuickLog = { open, openLabel, readLabel, pickPhoto };
})();
