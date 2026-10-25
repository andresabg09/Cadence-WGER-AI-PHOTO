// The units picker (weight, height, liquids) used by the first-use flow, the one-time welcome and Ajustes.
(function () {
  const OPTIONS = [
    ['weight', 'PESO', [['kg', 'Kilogramos'], ['lb', 'Libras']]],
    ['height', 'ESTATURA', [['cm', 'Centímetros'], ['ft', 'Pies y pulgadas']]],
    ['liquid', 'AGUA Y LÍQUIDOS', [['ml', 'Mililitros'], ['oz', 'Onzas']]],
  ];

  const sample = (u) => ({
    weight: u.weight === 'lb' ? '165 lb' : '75 kg',
    height: u.height === 'ft' ? '5 pies 9 pulgadas' : '175 cm',
    glass: u.liquid === 'oz' ? '8 oz' : '250 ml',
  });

  // Draws the picker inside `box` and calls onChange(units) with every tap. Returns a function that reads the choice.
  function mount(box, start, onChange) {
    const value = { weight: start.weight, height: start.height, liquid: start.liquid };
    const draw = () => {
      const s = sample(value);
      box.innerHTML = OPTIONS.map(([key, label, opts]) => `<div class="un-row"><span class="un-label">${label}</span>
        <div class="un-seg" role="group" aria-label="${label}">${opts.map(([v, name]) => `<button type="button" data-key="${key}" data-v="${v}" aria-pressed="${value[key] === v}">${name}</button>`).join('')}</div></div>`).join('')
        + `<div class="un-preview"><span class="un-label">ASÍ LO VERÁS</span>
          <div><span>Peso</span><b>${s.weight}</b></div><div><span>Estatura</span><b>${s.height}</b></div><div><span>Un vaso de agua</span><b>${s.glass}</b></div></div>`;
      box.querySelectorAll('.un-seg button').forEach((b) => b.addEventListener('click', () => {
        value[b.dataset.key] = b.dataset.v;
        if (window.sfx) sfx.play('pick');
        draw();
        if (onChange) onChange({ ...value });
      }));
    };
    draw();
    return () => ({ ...value });
  }

  // Ajustes -> Unidades: a sheet that saves to the server and updates this device at once.
  function openSheet(onSaved) {
    const scrim = document.createElement('div');
    scrim.className = 'sheet-scrim';
    const sheet = document.createElement('div');
    sheet.className = 'entry-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Unidades');
    sheet.innerHTML = `<h3 class="disp" style="margin:0 0 4px;">Unidades</h3>
      <p style="margin:0 0 16px;font-size:12px;color:var(--ink-soft);line-height:1.5;">Elige cómo ver tus medidas. Cambiarlo no altera tus datos: solo cómo se muestran. Los alimentos sólidos siempre van en gramos.</p>
      <div id="unBox"></div>
      <div class="form-error" id="unErr" style="margin-top:10px;"></div>
      <div class="sheet-actions"><button class="btn-primary" id="unSave">Guardar</button></div>`;
    document.body.append(scrim, sheet);
    pushOverlay(() => { scrim.remove(); sheet.remove(); });
    scrim.addEventListener('click', () => dismissOverlay());
    const read = mount(sheet.querySelector('#unBox'), window.cadenceUnits.get());
    sheet.querySelector('#unSave').addEventListener('click', async () => {
      try {
        const me = await apiPut('api/units', read());
        cadenceUnits.set(me.units);
        swrClear();
        if (window.sfx) sfx.play('save');
        dismissOverlay(() => onSaved && onSaved(me));
      } catch (err) {
        const e = sheet.querySelector('#unErr');
        e.textContent = err.message || 'No se pudo guardar';
        e.classList.add('show');
      }
    });
  }

  window.cadenceUnitsUI = { mount, openSheet };
})();
