// Fetch helpers shared across pages. Relative URLs on purpose - nginx
// exposes this service under /cadence/, and absolute paths would resolve
// against the domain root instead of that prefix (see nginx.conf).

async function apiGet(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiPost(path, body, { isFormData = false } = {}) {
  const response = await fetch(path, {
    method: 'POST',
    headers: isFormData ? undefined : { 'Content-Type': 'application/json' },
    body: isFormData ? body : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiDelete(path) {
  const response = await fetch(path, { method: 'DELETE' });
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function safeText(response) {
  try {
    const data = await response.json();
    return data.detail || JSON.stringify(data);
  } catch {
    // Not JSON (a proxy page, a crash): statusText is empty on HTTP/2, so say the code.
    return response.statusText || `Error ${response.status} del servidor`;
  }
}

function showToast(message, kind = 'error') {
  const toast = document.createElement('div');
  toast.className = `toast ${kind}`;
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

// ---- Banners (mockup "Estados y errores") --------------------------------
function showBanner(id, message, actionLabel, onAction) {
  hideBanner(id);
  const banner = document.createElement('div');
  banner.className = 'banner';
  banner.id = `banner-${id}`;
  banner.setAttribute('role', 'status');
  const text = document.createElement('span');
  text.textContent = message;
  banner.appendChild(text);
  if (actionLabel) {
    const btn = document.createElement('button');
    btn.textContent = actionLabel;
    btn.addEventListener('click', onAction);
    banner.appendChild(btn);
  }
  document.body.appendChild(banner);
}

function hideBanner(id) {
  const existing = document.getElementById(`banner-${id}`);
  if (existing) existing.remove();
}

// ---- Offline queue: confirmed plates are kept and sent when we're back ----
const PENDING_KEY = 'cadence_pending';

function readPending() {
  try { return JSON.parse(localStorage.getItem(PENDING_KEY) || '[]'); } catch { return []; }
}

function writePending(list) {
  try { localStorage.setItem(PENDING_KEY, JSON.stringify(list)); } catch { /* storage unavailable */ }
}

function queuePending(payload) {
  const list = readPending();
  list.push(payload);
  writePending(list);
}

function isNetworkFailure(err) {
  return !navigator.onLine || err instanceof TypeError;
}

// Sends every queued plate; stops at the first failure so order is kept.
async function flushPending() {
  let list = readPending();
  let sent = 0;
  while (list.length) {
    try {
      await apiPost('api/confirm', list[0]);
    } catch (err) {
      if (isNetworkFailure(err)) break;
      throw err;
    }
    list = list.slice(1);
    writePending(list);
    sent += 1;
  }
  return sent;
}

// ---- Images: downscale before upload (faster on mobile data, cheaper for the model) ----
async function prepareImage(file, maxDim = 1280) {
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
    const draw = (max) => {
      const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return canvas;
    };
    const blob = await new Promise((resolve) => draw(maxDim).toBlob(resolve, 'image/jpeg', 0.85));
    const thumb = draw(800).toDataURL('image/jpeg', 0.75); // also the source for per-ingredient crops
    return { blob: blob || file, thumb };
  } catch {
    return { blob: file, thumb: null };
  }
}

const SCAN_SESSION_KEYS = ['cadence_analyze_result', 'cadence_photos', 'cadence_meal'];
function clearScanSession() {
  SCAN_SESSION_KEYS.forEach((key) => sessionStorage.removeItem(key));
}

// ---- Photos of the plate being confirmed (one or several) and per-ingredient crops ----
function readPhotos() {
  try { return JSON.parse(sessionStorage.getItem('cadence_photos') || '[]'); } catch { return []; }
}

function writePhotos(list) {
  try { sessionStorage.setItem('cadence_photos', JSON.stringify(list)); } catch { /* quota: the plate still works without photos */ }
}

const _imageCache = new Map();
function loadImage(src) {
  if (!_imageCache.has(src)) {
    _imageCache.set(src, new Promise((resolve) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => resolve(null);
      img.src = src;
    }));
  }
  return _imageCache.get(src);
}

// Square, zoomed and centred on the ingredient's zone. box = [x, y, w, h] as 0-1 fractions.
async function cropThumb(src, box, size = 140) {
  const img = await loadImage(src);
  if (!img) return null;
  const W = img.naturalWidth;
  const H = img.naturalHeight;
  const [bx, by, bw, bh] = box;
  const cx = (bx + bw / 2) * W;
  const cy = (by + bh / 2) * H;
  const shortSide = Math.min(W, H);
  // 15% margin around the zone, never tighter than a fifth of the photo, never beyond it.
  let side = Math.max(bw * W, bh * H) * 1.15;
  side = Math.min(Math.max(side, shortSide * 0.2), shortSide);
  const sx = Math.max(0, Math.min(W - side, cx - side / 2));
  const sy = Math.max(0, Math.min(H - side, cy - side / 2));
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  canvas.getContext('2d').drawImage(img, sx, sy, side, side, 0, 0, size, size);
  return canvas.toDataURL('image/jpeg', 0.8);
}

// ---- The diary keeps each entry's own crop (localStorage, newest 150) ----
const THUMBS_KEY = 'cadence_thumbs';

function readThumbs() {
  try { return JSON.parse(localStorage.getItem(THUMBS_KEY) || '{}'); } catch { return {}; }
}

// created[i] is the diary entry of the i-th item we sent; crops[i] is that item's crop (or null).
function rememberThumbs(created, crops) {
  if (!created || !created.length) return;
  const map = readThumbs();
  created.forEach((entry, i) => { if (crops[i]) map[entry.diary_entry_id] = crops[i]; });
  const ids = Object.keys(map);
  if (ids.length > 150) ids.slice(0, ids.length - 150).forEach((id) => delete map[id]);
  try { localStorage.setItem(THUMBS_KEY, JSON.stringify(map)); } catch { /* storage full or unavailable */ }
}
