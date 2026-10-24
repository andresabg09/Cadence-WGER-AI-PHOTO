// A date picker in the app's own style (the browser's native one is dated and, in dark mode, hard to see).
// pickDate("1995-06-15", { maxIso, minYear }) -> Promise<"YYYY-MM-DD" | null>
(function () {
  const MONTHS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const pad = (n) => String(n).padStart(2, '0');
  const daysIn = (y, m) => new Date(y, m, 0).getDate();

  window.formatDateEs = (iso) => (iso
    ? new Date(`${iso}T12:00:00`).toLocaleDateString('es', { day: 'numeric', month: 'long', year: 'numeric' })
    : '');

  window.pickDate = function pickDate(initialIso, { maxIso, minYear } = {}) {
    return new Promise((resolve) => {
      const max = maxIso ? new Date(`${maxIso}T12:00:00`) : new Date();
      const maxY = max.getFullYear();
      const minY = minYear || maxY - 100;
      let [y, m, d] = initialIso ? initialIso.split('-').map(Number) : [Math.min(maxY, 1995), 6, 15];
      let settled = false;
      let result = null; // set by "Listo"; closing any other way leaves null
      const done = (value) => { if (!settled) { settled = true; resolve(value); } };

      const scrim = document.createElement('div');
      scrim.className = 'sheet-scrim';
      const sheet = document.createElement('div');
      sheet.className = 'entry-sheet picker-sheet';
      sheet.setAttribute('role', 'dialog');
      sheet.setAttribute('aria-label', 'Elegir fecha');
      document.body.append(scrim, sheet);
      pushOverlay(() => { scrim.remove(); sheet.remove(); done(result); });
      scrim.addEventListener('click', () => dismissOverlay());

      const column = (kind, items, selected) => `<div class="pick-col" data-kind="${kind}" role="listbox">${items.map(([value, label]) =>
        `<button type="button" class="pick-item${value === selected ? ' on' : ''}" data-value="${value}" role="option" aria-selected="${value === selected}">${label}</button>`).join('')}</div>`;

      function render() {
        d = Math.min(d, daysIn(y, m));
        const days = Array.from({ length: daysIn(y, m) }, (_, i) => [i + 1, String(i + 1)]);
        const months = MONTHS.map((name, i) => [i + 1, name]);
        const years = Array.from({ length: maxY - minY + 1 }, (_, i) => [maxY - i, String(maxY - i)]);
        sheet.innerHTML = `
          <h3 class="disp" style="margin:0 0 4px;font-size:17px;">Fecha de nacimiento</h3>
          <p class="pick-preview" id="pickPreview">${formatDateEs(`${y}-${pad(m)}-${pad(d)}`)}</p>
          <div class="pick-cols">${column('d', days, d)}${column('m', months, m)}${column('y', years, y)}</div>
          <div class="sheet-actions"><button type="button" class="btn-primary" id="pickOk">Listo</button></div>`;
        sheet.querySelectorAll('.pick-col').forEach((col) => {
          const on = col.querySelector('.on');
          if (on) col.scrollTop = on.offsetTop - col.clientHeight / 2 + on.offsetHeight / 2;
          col.addEventListener('click', (e) => {
            const item = e.target.closest('.pick-item');
            if (!item) return;
            const value = Number(item.dataset.value);
            if (col.dataset.kind === 'd') d = value; else if (col.dataset.kind === 'm') m = value; else y = value;
            const kind = col.dataset.kind;
            const keep = [...sheet.querySelectorAll('.pick-col')].map((c) => c.scrollTop);
            render();
            sheet.querySelectorAll('.pick-col').forEach((c, i) => {
              c.scrollTop = keep[i]; // the other columns do not jump
              if (c.dataset.kind === kind) {  // the one you tapped glides the choice to the middle
                const on = c.querySelector('.on');
                c.scrollTo({ top: on.offsetTop - c.clientHeight / 2 + on.offsetHeight / 2, behavior: 'smooth' });
              }
            });
          });
        });
        sheet.querySelector('#pickOk').addEventListener('click', () => {
          const iso = `${y}-${pad(m)}-${pad(d)}`;
          if (new Date(`${iso}T12:00:00`) > max) { sheet.querySelector('#pickPreview').textContent = 'Esa fecha todavía no ha llegado'; return; }
          result = iso;
          dismissOverlay();
        });
      }
      render();
    });
  };
})();
