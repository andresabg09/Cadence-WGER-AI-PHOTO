// How measures are SHOWN. Everything is stored and calculated in metric (kg, cm, ml, g); each person only chooses how
// to see it: weight in kg or lb, height in cm or feet+inches, liquids in ml or fl oz. Solid food is always grams.
// The choice lives on the server (me.units); this file keeps a copy so pages paint right away.
(function () {
  const KEY = 'cadence_units';
  const LB_PER_KG = 2.2046226;
  const CM_PER_IN = 2.54;
  const ML_PER_OZ = 29.5735;
  const METRIC = { weight: 'kg', height: 'cm', liquid: 'ml', chosen: false };
  const PANAMA = { weight: 'lb', height: 'ft', liquid: 'oz', chosen: false }; // what the first-use flow offers already chosen

  let current = Object.assign({}, METRIC);
  try { const saved = JSON.parse(localStorage.getItem(KEY) || 'null'); if (saved && saved.weight) current = Object.assign({}, METRIC, saved); } catch { /* no storage */ }

  const trim = (n, dec) => String(Number(n.toFixed(dec)));
  const es = (n) => Number(n).toLocaleString('es');

  const U = {
    METRIC, PANAMA, LB_PER_KG, ML_PER_OZ,
    get() { return current; },
    // Returns true when what this device showed changes (the pages then repaint)
    set(units) {
      const before = JSON.stringify(current);
      current = Object.assign({}, METRIC, units || {});
      try { localStorage.setItem(KEY, JSON.stringify(current)); } catch { /* no storage */ }
      return before !== JSON.stringify(current);
    },
    // Weight
    isLb: () => current.weight === 'lb',
    weightLabel: () => (current.weight === 'lb' ? 'lb' : 'kg'),
    weightValue: (kg) => (current.weight === 'lb' ? kg * LB_PER_KG : kg),
    weightToKg: (value) => (current.weight === 'lb' ? value / LB_PER_KG : value),
    fmtWeight: (kg, dec = 1) => (kg == null ? '–' : `${trim(U.weightValue(kg), dec)} ${U.weightLabel()}`),
    // A change of weight per month (the server speaks in pounds): "4 lb al mes" or "1.8 kg al mes"
    paceValue: (lb) => (current.weight === 'lb' ? lb : lb / LB_PER_KG),
    paceToLb: (value) => (current.weight === 'lb' ? value : value * LB_PER_KG),
    // "unas 4 lb": it is an estimate, so it is said in halves, never as 3.87
    fmtChange: (lb) => `${trim(Math.max(0.5, Math.round(Math.abs(U.paceValue(lb)) * 2) / 2), 1)} ${U.weightLabel()}`,
    // "unas 4 lb" / "cerca de 1 kg": how a monthly change is said in a sentence
    aboutChange(lb) { const v = Math.max(0.5, Math.round(Math.abs(U.paceValue(lb)) * 2) / 2); return `${v <= 1 ? 'cerca de' : 'unas'} ${trim(v, 1)} ${U.weightLabel()}`; },
    // Height
    isFt: () => current.height === 'ft',
    heightParts(cm) { const inches = Math.round(cm / CM_PER_IN); return { ft: Math.floor(inches / 12), inch: inches % 12 }; },
    heightToCm: (ft, inch) => Math.round((Number(ft) * 12 + Number(inch)) * CM_PER_IN),
    fmtHeight(cm) {
      if (cm == null) return '–';
      if (current.height !== 'ft') return `${Math.round(cm)} cm`;
      const p = U.heightParts(cm);
      return `${p.ft} pies ${p.inch} pulgadas`;
    },
    // Liquids and amounts (1 ml counts as 1 g for a liquid)
    isOz: () => current.liquid === 'oz',
    volumeLabel: () => (current.liquid === 'oz' ? 'oz' : 'ml'),
    volumeValue: (ml) => (current.liquid === 'oz' ? ml / ML_PER_OZ : ml),
    volumeToMl: (value) => (current.liquid === 'oz' ? value * ML_PER_OZ : value),
    fmtVolume(ml) {
      if (current.liquid === 'oz') return `${trim(ml / ML_PER_OZ, 1)} oz`;
      return `${es(Math.round(ml))} ml`;
    },
    fmtAmount: (grams, liquid) => (liquid ? U.fmtVolume(grams) : `${Math.round(grams)} g`),
    // One tap on + / − for a liquid: a whole ounce, or the usual step in ml
    liquidStep: (fallback) => (current.liquid === 'oz' ? ML_PER_OZ : fallback),
    // Water is counted in glasses: 8 oz = 237 ml, so 11 glasses read 88 oz (not 88.2)
    waterNumber: (ml) => (current.liquid === 'oz' ? Number((ml / 237 * 8).toFixed(1)) : Math.round(ml)),
    fmtWater: (ml) => (current.liquid === 'oz' ? `${Number((ml / 237 * 8).toFixed(1))} oz` : `${es(Math.round(ml))} ml`),
    // A glass of water: 250 ml, or 8 oz (about 237 ml)
    glassMl: () => (current.liquid === 'oz' ? 237 : 250),
    glassLabel: () => (current.liquid === 'oz' ? '8 oz' : '250 ml'),
  };
  window.cadenceUnits = U;
})();
