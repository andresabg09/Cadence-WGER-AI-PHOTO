// "Alimento propio": a sheet to type a food's macros per 100 g (own food, or a scanned product the
// catalog does not know). Saved in cadence (POST /api/foods); onSaved gets {id, name, energy_kcal_100g}.
function openFoodSheet(initial, onSaved) {
  const start = initial || {};
  const num = (v) => (v == null || Number.isNaN(Number(v)) ? '' : String(Math.round(Number(v) * 10) / 10));
  const scrim = document.createElement('div');
  scrim.className = 'sheet-scrim';
  const sheet = document.createElement('div');
  sheet.className = 'entry-sheet';
  sheet.setAttribute('role', 'dialog');
  sheet.setAttribute('aria-label', 'Alimento propio');
  sheet.innerHTML = `
    <h3 class="disp" style="margin:0 0 4px;font-size:17px;">${start.barcode ? 'Producto escaneado' : 'Alimento propio'}</h3>
    <p style="margin:0 0 14px;font-size:12px;color:var(--ink-soft);line-height:1.5;">${start.barcode
      ? 'Revisa los valores (por cada 100 g) y guárdalos: la próxima vez saldrá solo al escanear.'
      : 'Escribe los valores por cada 100 g (están en la etiqueta). Solo tú lo verás.'}</p>
    <label class="field"><span>NOMBRE</span><input class="input" id="fName" maxlength="80" value="${escapeHtml(start.name || '')}" placeholder="Ej.: Pan de la abuela" autocomplete="off"></label>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
      <label class="field"><span>CALORÍAS</span><div class="input-unit"><input class="input" id="fKcal" type="number" inputmode="decimal" min="0" max="950" step="any" value="${num(start.kcal)}"><i>kcal</i></div></label>
      <label class="field"><span>PROTEÍNA</span><div class="input-unit"><input class="input" id="fProt" type="number" inputmode="decimal" min="0" max="100" step="any" value="${num(start.protein)}"><i>g</i></div></label>
      <label class="field"><span>CARBOHIDRATOS</span><div class="input-unit"><input class="input" id="fCarb" type="number" inputmode="decimal" min="0" max="100" step="any" value="${num(start.carbs)}"><i>g</i></div></label>
      <label class="field"><span>GRASA</span><div class="input-unit"><input class="input" id="fFat" type="number" inputmode="decimal" min="0" max="100" step="any" value="${num(start.fat)}"><i>g</i></div></label>
    </div>
    ${start.barcode ? `<div style="font-size:11px;color:var(--ink-soft);margin-top:6px;">Código: <span class="mono">${escapeHtml(start.barcode)}</span></div>` : ''}
    <div class="form-error" id="fErr" style="margin-top:10px;"></div>
    <div class="sheet-actions"><button class="btn-secondary" id="fCancel">Cancelar</button><button class="btn-primary" id="fSave">Guardar y usar</button></div>`;
  document.body.append(scrim, sheet);
  pushOverlay(() => { scrim.remove(); sheet.remove(); });
  scrim.addEventListener('click', () => dismissOverlay());
  const $ = (id) => sheet.querySelector(`#${id}`);
  $('fCancel').addEventListener('click', () => dismissOverlay());
  setTimeout(() => $(start.name ? 'fKcal' : 'fName').focus(), 50);
  $('fSave').addEventListener('click', async () => {
    const err = $('fErr');
    err.classList.remove('show');
    const body = {
      name: $('fName').value.trim(),
      kcal: Number($('fKcal').value),
      protein: Number($('fProt').value || 0),
      carbs: Number($('fCarb').value || 0),
      fat: Number($('fFat').value || 0),
      barcode: start.barcode || null,
    };
    if (!body.name) { err.textContent = 'Ponle un nombre al alimento.'; err.classList.add('show'); return; }
    if (!$('fKcal').value || Number.isNaN(body.kcal)) { err.textContent = 'Escribe las calorías por 100 g.'; err.classList.add('show'); return; }
    $('fSave').disabled = true;
    try {
      const food = await apiPost('api/foods', body);
      if (window.sfx) sfx.play('save');
      dismissOverlay(() => onSaved(food));
    } catch (e) {
      err.textContent = e.message || 'No se pudo guardar';
      err.classList.add('show');
      $('fSave').disabled = false;
    }
  });
}
