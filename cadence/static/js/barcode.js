// Barcode reading on a playing <video>. Android Chrome has BarcodeDetector; iPhone Safari and desktop
// browsers do not, so the bundled ZXing reader (js/vendor/zxing.min.js, Apache-2.0) is loaded only then.
const BARCODE_FORMATS = ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128'];

function loadZxing() {
  if (window.ZXing) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'static/js/vendor/zxing.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('No se pudo cargar el lector de códigos'));
    document.head.appendChild(s);
  });
}

// Calls onCode(text) once with the first code read; returns stop().
async function startBarcodeScan(video, onCode) {
  let stopped = false;
  const stop = () => { stopped = true; };
  const done = (text) => { if (!stopped) { stopped = true; onCode(text); } };
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', { willReadFrequently: true });

  let read;
  if ('BarcodeDetector' in window) {
    let detector = null;
    try { detector = new window.BarcodeDetector({ formats: BARCODE_FORMATS }); } catch { detector = null; }
    if (detector) read = async () => { const found = await detector.detect(video); return found.length ? found[0].rawValue : null; };
  }
  if (!read) {
    await loadZxing();
    const Z = window.ZXing;
    const reader = new Z.MultiFormatReader();
    const hints = new Map();
    hints.set(Z.DecodeHintType.POSSIBLE_FORMATS, [Z.BarcodeFormat.EAN_13, Z.BarcodeFormat.EAN_8, Z.BarcodeFormat.UPC_A, Z.BarcodeFormat.UPC_E, Z.BarcodeFormat.CODE_128]);
    hints.set(Z.DecodeHintType.TRY_HARDER, true);
    reader.setHints(hints);
    read = async () => {
      const scale = Math.min(1, 720 / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      try {
        const bitmap = new Z.BinaryBitmap(new Z.HybridBinarizer(new Z.HTMLCanvasElementLuminanceSource(canvas)));
        return reader.decode(bitmap).getText();
      } catch { return null; } // nothing readable in this frame
    };
  }

  (async function loop() {
    while (!stopped) {
      if (video.readyState >= 2 && video.videoWidth) {
        try { const text = await read(); if (text) { done(text); return; } } catch { /* try the next frame */ }
      }
      await new Promise((r) => setTimeout(r, 140));
    }
  })();
  return stop;
}

// For when the camera cannot read it (worn label, no permission): type the digits.
function openBarcodeTyping(onCode) {
  const scrim = document.createElement('div');
  scrim.className = 'sheet-scrim';
  const sheet = document.createElement('div');
  sheet.className = 'entry-sheet';
  sheet.setAttribute('role', 'dialog');
  sheet.innerHTML = `
    <h3 class="disp" style="margin:0 0 4px;font-size:17px;">Escribir el código</h3>
    <p style="margin:0 0 14px;font-size:12px;color:var(--ink-soft);">Los números que van debajo de las barras.</p>
    <input class="input mono" id="bcInput" inputmode="numeric" maxlength="14" placeholder="7501055300004" autocomplete="off">
    <div class="form-error" id="bcErr" style="margin-top:10px;"></div>
    <div class="sheet-actions"><button class="btn-primary" id="bcGo">Buscar</button></div>`;
  document.body.append(scrim, sheet);
  pushOverlay(() => { scrim.remove(); sheet.remove(); });
  scrim.addEventListener('click', () => dismissOverlay());
  const input = sheet.querySelector('#bcInput');
  setTimeout(() => input.focus(), 50);
  const go = () => {
    const code = input.value.replace(/\D/g, '');
    if (code.length < 6) { const e = sheet.querySelector('#bcErr'); e.textContent = 'Escribe todos los números del código.'; e.classList.add('show'); return; }
    dismissOverlay(() => onCode(code));
  };
  sheet.querySelector('#bcGo').addEventListener('click', go);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') go(); });
}
