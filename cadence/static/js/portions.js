// How much did you eat, for people who do not weigh their food. Three ways, each person chooses (me.units.portion):
//   home  = cups, spoons, units and slices ("1½ tazas de arroz")
//   photo = a hand, a card or a fork next to the plate gives the photo a scale; amounts are then shown as "≈ 1 taza"
//   grams = the exact way, for whoever weighs
// Everything is still stored in grams: this only changes how an amount is shown and entered. The grams of each measure are a
// fixed, visible table (household averages), never the AI.
(function () {
  // [words that identify the food (Spanish or English, as the photo or the catalog names it), grams of 1 cup, 1 unit, 1 slice,
  //  'vaso' when it is drunk from a glass]
  const FOODS = [
    [['arroz', 'rice'], 160],
    [['pasta', 'espagueti', 'spaghetti', 'macarron', 'fideo', 'noodle'], 140],
    [['frijol', 'poroto', 'bean', 'lenteja', 'lentil', 'garbanzo', 'chickpea', 'guandu'], 170],
    [['avena', 'oatmeal', 'porridge'], 235],
    [['cereal', 'granola', 'corn flakes'], 40],
    [['ensalada', 'lechuga', 'salad', 'lettuce', 'espinaca', 'spinach'], 50],
    [['brocoli', 'broccoli', 'zanahoria', 'carrot', 'vegetal', 'verdura', 'vegetable', 'vainita', 'maiz', 'corn'], 150],
    [['pure', 'mashed'], 210],
    [['yogur', 'yogurt'], 245],
    [['helado', 'ice cream'], 130],
    [['sopa', 'soup', 'caldo', 'broth', 'sancocho', 'crema de'], 245],
    [['leche', 'milk', 'jugo', 'juice', 'batido', 'smoothie', 'cafe', 'coffee', ' te ', ' tea', 'refresco', 'soda', 'chicha'], 240, 0, 0, 'vaso'],
    [['huevo', 'egg'], 240, 50],
    [['banano', 'banana', 'guineo'], 150, 120],
    [['platano', 'plantain', 'patacon', 'tajada'], 150, 160],
    [['manzana', 'apple'], 125, 180],
    [['naranja', 'orange', 'mandarina'], 180, 140],
    [['pera', 'pear'], 140, 180],
    [['durazno', 'melocoton', 'peach'], 155, 150],
    [['mango'], 165, 200],
    [['aguacate', 'avocado'], 150, 150],
    [['tomate', 'tomato'], 180, 120],
    [[' papa ', ' papas ', 'potato'], 150, 170],
    [['yuca', 'cassava'], 140, 200],
    [['tortilla'], 0, 30],
    [['arepa'], 0, 90],
    [['empanada'], 0, 100],
    [[' pan ', 'bread', 'pan de molde', 'toast', 'tostada'], 0, 0, 30],
    [['bun', ' roll', 'pan de hamburguesa', 'pan de perro'], 0, 60],
    [['galleta', 'cookie', 'cracker'], 0, 12],
    [['pechuga', 'breast'], 140, 170],
    [['muslo', 'thigh', 'presa'], 140, 110],
    [['salchicha', 'sausage', 'hot dog'], 0, 50],
    [['carne', 'beef', ' res ', 'cerdo', 'pork', 'pollo', 'chicken', 'pescado', 'fish', 'atun', 'tuna', 'filete', 'bistec'], 140],
    [['queso', 'cheese'], 110, 0, 20],
    [['jamon', 'ham'], 140, 0, 20],
    [['pizza'], 0, 0, 110],
    [['pastel', 'cake', 'torta', 'bizcocho'], 0, 0, 80],
  ];
  // Fats and sauces are counted in spoons: a cup of oil is never what was eaten.
  const SPOON = [
    [['aceite', 'oil'], 14], [['mantequilla', 'butter', 'margarina'], 14], [['mayonesa', 'mayo'], 14], [['azucar', 'sugar'], 12],
    [['mani', 'peanut butter', 'crema de cacahuate'], 16], [['miel', 'honey', 'sirope', 'syrup'], 21], [['salsa', 'sauce', 'ketchup', 'aderezo', 'dressing'], 16],
    [['queso rallado', 'parmesan', 'grated'], 6],
  ];
  const CUP_SOLID = 150;
  const CUP_LIQUID = 240;
  const plain = (t) => ` ${String(t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')} `;
  const has = (text, words) => words.some((w) => text.includes(w)); // the text is padded with spaces: ' res ' is a whole word

  // Measures that make sense for this food, the most natural first. Each: {key, one, many, g}
  function measuresFor(names, liquid) {
    const text = plain([].concat(names).join(' '));
    const spoon = SPOON.find(([words]) => has(text, words));
    if (spoon) return [{ key: 'tbsp', one: 'cucharada', many: 'cucharadas', g: spoon[1] }, { key: 'tsp', one: 'cucharadita', many: 'cucharaditas', g: Math.round(spoon[1] / 3 * 10) / 10 }];
    const food = FOODS.find(([words]) => has(text, words));
    const list = [];
    if (food && food[2]) list.push({ key: 'unit', one: 'unidad', many: 'unidades', g: food[2] });
    if (food && food[3]) list.push({ key: 'slice', one: 'rebanada', many: 'rebanadas', g: food[3] });
    const cup = food && food[1] !== undefined ? food[1] : (liquid ? CUP_LIQUID : CUP_SOLID);
    const glass = food && food[4] === 'vaso';
    if (cup) list.push({ key: 'cup', one: glass ? 'vaso' : 'taza', many: glass ? 'vasos' : 'tazas', g: cup });
    list.push({ key: 'tbsp', one: 'cucharada', many: 'cucharadas', g: 15 });
    return list;
  }

  const FRACTIONS = { 0.25: '¼', 0.5: '½', 0.75: '¾' };
  function fmtQty(q) {
    const whole = Math.floor(q + 1e-9);
    const frac = Math.round((q - whole) * 4) / 4;
    if (frac === 1) return String(whole + 1);
    return `${whole || (frac ? '' : '0')}${FRACTIONS[frac] || ''}`;
  }
  // Steps a person can actually picture: quarters under 1, halves up to 3, then whole ones.
  function stepQty(q, direction) {
    const step = (direction > 0 ? q : q - 0.01) < 1 ? 0.25 : (direction > 0 ? q : q - 0.01) < 3 ? 0.5 : 1;
    return Math.max(0.25, Math.round((q + direction * step) / step) * step);
  }
  const roundQty = (q) => Math.max(0.25, q < 1 ? Math.round(q * 4) / 4 : q < 3 ? Math.round(q * 2) / 2 : Math.round(q));
  const label = (m, q) => `${fmtQty(q)} ${q > 1 ? m.many : m.one}`;

  // The measure that reads best for an amount: a whole unit or slice if it is one; else cups, else spoons for small amounts.
  function best(grams, names, liquid) {
    const list = measuresFor(names, liquid);
    const pick = list.find((m) => (m.key === 'unit' || m.key === 'slice') && grams / m.g >= 0.5 && grams / m.g <= 6)
      || list.find((m) => m.key === 'cup' && grams / m.g >= 0.25)
      || list.find((m) => m.key === 'tbsp') || list[0];
    return { measure: pick, qty: roundQty(grams / pick.g) };
  }
  const describe = (grams, names, liquid) => { const b = best(grams, names, liquid); return label(b.measure, b.qty); };

  const MODES = [
    ['home', 'Medidas de casa', 'Tazas, cucharadas, unidades y rebanadas. Lo más fácil si no pesas tu comida.', 'cooking-pot'],
    ['photo', 'Referencia en la foto', 'Pon tu mano, una tarjeta o un tenedor junto al plato: la foto calcula mejor el tamaño.', 'camera'],
    ['grams', 'Gramos', 'La forma exacta, si pesas tu comida.', 'scales'],
  ];
  const mode = () => (window.cadenceUnits && cadenceUnits.get().portion) || null;

  // The three options as big buttons inside `box`; onPick(mode) with every tap.
  function mount(box, start, onPick) {
    let value = start;
    const draw = () => {
      box.innerHTML = MODES.map(([key, title, text, ico]) => `<button type="button" class="pm-opt" data-mode="${key}" aria-pressed="${value === key}">
        <span class="pm-ico"><i data-ico="${ico}"></i></span><span class="pm-txt"><b>${title}</b><span>${text}</span></span></button>`).join('');
      box.querySelectorAll('.pm-opt').forEach((b) => b.addEventListener('click', () => { value = b.dataset.mode; if (window.sfx) sfx.play('pick'); draw(); if (onPick) onPick(value); }));
    };
    draw();
    return () => value;
  }

  async function save(value) {
    const me = await apiPut('api/portion', { mode: value });
    cadenceUnits.set(me.units);
    return me;
  }

  // A sheet to choose (Ajustes, or the first time a meal is logged). onDone(mode) after saving.
  function choose(onDone, { first = false } = {}) {
    const scrim = document.createElement('div');
    scrim.className = 'sheet-scrim';
    const sheet = document.createElement('div');
    sheet.className = 'entry-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Cómo medir tus porciones');
    sheet.innerHTML = `<h3 class="disp" style="margin:0 0 4px;">${first ? '¿Cómo prefieres medir tus porciones?' : 'Cómo medir tus porciones'}</h3>
      <p style="margin:0 0 14px;font-size:12px;color:var(--ink-soft);line-height:1.5;">Elige lo que te resulte más sencillo. Puedes cambiarlo cuando quieras en Ajustes.</p>
      <div id="pmBox" class="pm-box"></div><div class="form-error" id="pmErr" style="margin-top:10px;"></div>
      <div class="sheet-actions"><button class="btn-primary" id="pmSave">${first ? 'Listo' : 'Guardar'}</button></div>`;
    document.body.append(scrim, sheet);
    pushOverlay(() => { scrim.remove(); sheet.remove(); });
    if (!first) scrim.addEventListener('click', () => dismissOverlay());
    const read = mount(sheet.querySelector('#pmBox'), mode() || 'home');
    sheet.querySelector('#pmSave').addEventListener('click', async () => {
      try {
        const value = read();
        await save(value);
        if (window.sfx) sfx.play('save');
        dismissOverlay(() => onDone && onDone(value));
      } catch (err) {
        const e = sheet.querySelector('#pmErr');
        e.textContent = err.message || 'No se pudo guardar';
        e.classList.add('show');
      }
    });
  }

  // The first time a meal is logged without having chosen: ask once. Resolves with the mode.
  function ensureChosen() {
    return new Promise((resolve) => { if (mode()) resolve(mode()); else choose(resolve, { first: true }); });
  }

  const title = (key) => (MODES.find((m) => m[0] === key) || [])[1] || 'Sin elegir';
  window.cadencePortions = { MODES, mode, measuresFor, best, describe, label, fmtQty, stepQty, roundQty, mount, save, choose, ensureChosen, title };
})();
