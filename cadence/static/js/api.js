// Fetch helpers shared across pages. Relative URLs on purpose - nginx
// exposes this service under /cadence/, and absolute paths would resolve
// against the domain root instead of that prefix (see nginx.conf).

// ---- Navigation: the system Back button must never surprise ----
// Rules (also in CLAUDE.md): (1) anything that opens on top of a screen (sheet, calendar, photo
// viewer) takes one history step, so Back closes it and leaves you where you were; (2) a flow
// started from the diary (scan -> confirm, search -> confirm) occupies ONE history entry: moving
// inside it replaces, and finishing or cancelling steps back to the diary.
const _overlays = []; // close functions, innermost last
let _afterDismiss = null;

function pushOverlay(close) {
  _overlays.push(close);
  history.pushState({ cadenceOverlay: _overlays.length }, '');
}

// Used by every "close" control (X, backdrop, Esc, Save): one step back; popstate does the closing.
function dismissOverlay(after) {
  if (!_overlays.length) { if (after) after(); return; }
  _afterDismiss = after || null;
  history.back();
}

window.addEventListener('popstate', (e) => {
  const depth = (e.state && e.state.cadenceOverlay) || 0;
  while (_overlays.length > depth) {
    const close = _overlays.pop();
    try { close(); } catch { /* already gone */ }
  }
  if (_afterDismiss && _overlays.length === depth) {
    const fn = _afterDismiss;
    _afterDismiss = null;
    fn();
  }
});

// A reload leaves a stale "overlay" marker in the current entry: clear it.
if (history.state && history.state.cadenceOverlay) history.replaceState(null, '');

document.addEventListener('keydown', (e) => { if (e.key === 'Escape') dismissOverlay(); });

const FROM_INDEX_KEY = 'cadence_from_index';

// Finish or cancel a flow: back to the diary entry it started from, or to `fallback` when the
// flow was opened directly (a shortcut, a link, a reload).
function leaveFlow(fallback) {
  let fromIndex = false;
  try { fromIndex = sessionStorage.getItem(FROM_INDEX_KEY) === '1'; } catch { /* no storage */ }
  if (fromIndex && history.length > 1) {
    try { sessionStorage.removeItem(FROM_INDEX_KEY); } catch { /* no storage */ }
    history.back();
  } else {
    window.location.replace(fallback);
  }
}

document.addEventListener('click', (e) => {
  const link = e.target.closest && e.target.closest('a[data-replace], a[data-leave]');
  if (!link || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
  e.preventDefault();
  if (link.hasAttribute('data-leave')) leaveFlow(link.getAttribute('href'));
  else window.location.replace(link.getAttribute('href'));
});

// ---- Session: every data call needs the signed-in cookie; a 401 sends you to the login screen ----
const UID_KEY = 'cadence_uid';

function handleAuth(response) {
  // On the login screen a 401 is just "wrong password": the caller shows the server's message.
  if (response.status !== 401 || /\/login\.html$/.test(window.location.pathname)) return;
  const here = window.location.pathname.split('/').pop() + window.location.search;
  window.location.replace(`login.html?next=${encodeURIComponent(here)}`);
  throw new Error('Inicia sesión para continuar');
}

// What this device keeps per person (crops, notes, offline queue...) must not leak to the next person who signs in.
function rememberUser(me) {
  try {
    const previous = localStorage.getItem(UID_KEY);
    if (previous && previous !== String(me.id)) {
      Object.keys(localStorage)
        .filter((k) => k.startsWith('cadence_') && !['cadence_theme', 'cadence_visits', 'cadence_install_dismissed', UID_KEY].includes(k))
        .forEach((k) => localStorage.removeItem(k));
    }
    localStorage.setItem(UID_KEY, String(me.id));
  } catch { /* no storage */ }
}

// Signed in and set up, or on the way to the screen that fixes that. Returns the profile.
async function ensureSession({ needOnboarded = true } = {}) {
  const me = await apiGet('api/auth/me');
  rememberUser(me);
  if (needOnboarded && !me.onboarded) {
    window.location.replace('onboarding.html');
    throw new Error('Falta completar tu perfil');
  }
  return me;
}

async function signOut() {
  try { await apiPost('api/auth/logout', {}); } catch { /* the cookie is cleared server-side when reachable */ }
  window.location.replace('login.html');
}

async function apiGet(path) {
  const response = await fetch(path);
  handleAuth(response);
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiPost(path, body, { isFormData = false, timeoutMs = 90000 } = {}) {
  // A request that never answers must end in a visible error, not a button that does nothing.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(path, {
      method: 'POST',
      headers: isFormData ? undefined : { 'Content-Type': 'application/json' },
      body: isFormData ? body : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    if (err && err.name === 'AbortError') throw new Error('El servidor tardó demasiado en responder');
    throw err;
  } finally {
    clearTimeout(timer);
  }
  handleAuth(response);
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiPut(path, body) {
  const response = await fetch(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  handleAuth(response);
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiPatch(path, body) {
  const response = await fetch(path, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  handleAuth(response);
  if (!response.ok) throw new Error(await safeText(response));
  return response.json();
}

async function apiDelete(path) {
  const response = await fetch(path, { method: 'DELETE' });
  handleAuth(response);
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
    const canvas = draw(maxDim);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.88));
    // Same pixels as the upload: it is the source of every crop and the photo kept with the record.
    const thumb = canvas.toDataURL('image/jpeg', 0.88);
    return { blob: blob || file, thumb };
  } catch {
    return { blob: file, thumb: null };
  }
}

const SCAN_SESSION_KEYS = ['cadence_analyze_result', 'cadence_photos', 'cadence_meal', 'cadence_taken_at'];
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
async function cropThumb(src, box, size = 220, quality = 0.88) {
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
  // Never ask for more pixels than the zone has: upscaling is what made crops look soft.
  const out = Math.max(64, Math.min(size, Math.round(side)));
  canvas.width = canvas.height = out;
  const ctx = canvas.getContext('2d');
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(img, sx, sy, side, side, 0, 0, out, out);
  return canvas.toDataURL('image/jpeg', quality);
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

// ---- Photos and notes live on the server (cadence's own store); what is local is only a fallback ----
// created[i] is the diary entry of chosen[i]. Sends the plate photo(s) and a sharp crop per ingredient.
async function uploadMedia(created, chosen, photos) {
  if (!created || !created.length) return;
  const items = [];
  for (let i = 0; i < created.length; i += 1) {
    const item = chosen[i];
    if (!item) continue;
    const hasPhoto = item.photo != null && photos[item.photo];
    const crop = hasPhoto && item.box ? await cropThumb(photos[item.photo], item.box, 420, 0.9) : (item.crop || null);
    items.push({ entry_id: created[i].diary_entry_id, crop, photo: hasPhoto ? item.photo : null, box: item.box || null });
  }
  await apiPost('api/entry-media', { plate_id: created[0].diary_entry_id, photos, items }, { timeoutMs: 120000 });
}

function forgetLocal(entryId) {
  const thumbs = readThumbs(); delete thumbs[entryId];
  const links = readJsonKey(ENTRY_PLATE_KEY); delete links[entryId];
  try {
    localStorage.setItem(THUMBS_KEY, JSON.stringify(thumbs));
    localStorage.setItem(ENTRY_PLATE_KEY, JSON.stringify(links));
  } catch { /* nothing to free */ }
  writeNote(entryId, '');
}

// Entries saved before the server kept extras (or while it was unreachable): move what this
// device remembers up to the server. Returns true when something moved (the page may refresh).
async function syncLocalExtras(items) {
  let moved = false;
  const notes = readNotes();
  for (const item of items) {
    const id = item.diary_entry_id;
    try {
      const localNote = notes[id];
      if (localNote && !item.note) { await apiPut(`api/diary/${id}/note`, { note: localNote }); moved = true; }
      const crop = readThumbs()[id];
      const plate = readEntryPlate(id);
      if ((crop && !item.has_crop) || (plate && !item.plate_key)) {
        await apiPost('api/entry-media', {
          plate_id: `legacy-${id}`,
          photos: plate ? [plate.photo] : [],
          items: [{ entry_id: id, crop: item.has_crop ? null : crop || null, photo: plate ? 0 : null, box: plate ? plate.box : null }],
        });
        moved = true;
      }
      if (moved && (localNote || crop || plate)) forgetLocal(id);
    } catch { /* try again on the next visit */ }
  }
  return moved;
}

// ---- Notes ("observaciones") per diary entry: legacy local copy, moved to the server by syncLocalExtras ----
const NOTES_KEY = 'cadence_notes';

function readNotes() {
  try { return JSON.parse(localStorage.getItem(NOTES_KEY) || '{}'); } catch { return {}; }
}

function writeNote(entryId, text) {
  const notes = readNotes();
  const clean = (text || '').trim();
  if (clean) notes[entryId] = clean; else delete notes[entryId];
  try { localStorage.setItem(NOTES_KEY, JSON.stringify(notes)); } catch { /* storage full or unavailable */ }
}

// ---- The plate's photo per entry, so a past record can be opened and looked at again ----
const PLATES_KEY = 'cadence_plates';           // { "<plate>:<photo>": dataUrl (480 px) }
const ENTRY_PLATE_KEY = 'cadence_entry_plate'; // { "<entry id>": { key, box } }

function readJsonKey(key) {
  try { return JSON.parse(localStorage.getItem(key) || '{}'); } catch { return {}; }
}

function readEntryPlate(entryId) {
  const link = readJsonKey(ENTRY_PLATE_KEY)[entryId];
  if (!link) return null;
  const photo = readJsonKey(PLATES_KEY)[link.key];
  return photo ? { photo, box: link.box || null } : null;
}

async function downscale(src, maxDim = 480) {
  const img = await loadImage(src);
  if (!img) return null;
  const scale = Math.min(1, maxDim / Math.max(img.naturalWidth, img.naturalHeight));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(img.naturalWidth * scale);
  canvas.height = Math.round(img.naturalHeight * scale);
  canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.65);
}

// created[i] is the diary entry of chosen[i]; chosen[i].photo is an index into photos.
async function rememberPlate(created, chosen, photos) {
  if (!created || !created.length) return;
  const plates = readJsonKey(PLATES_KEY);
  const links = readJsonKey(ENTRY_PLATE_KEY);
  const plateId = created[0].diary_entry_id;
  for (let i = 0; i < created.length; i += 1) {
    const item = chosen[i];
    if (!item || item.photo == null || !photos[item.photo]) continue;
    const key = `${plateId}:${item.photo}`;
    if (!plates[key]) plates[key] = await downscale(photos[item.photo]);
    if (plates[key]) links[created[i].diary_entry_id] = { key, box: item.box || null };
  }
  const keys = Object.keys(plates);
  if (keys.length > 20) keys.slice(0, keys.length - 20).forEach((k) => delete plates[k]); // newest 20 plates
  const ids = Object.keys(links);
  if (ids.length > 150) ids.slice(0, ids.length - 150).forEach((id) => delete links[id]);
  try {
    localStorage.setItem(PLATES_KEY, JSON.stringify(plates));
    localStorage.setItem(ENTRY_PLATE_KEY, JSON.stringify(links));
  } catch { /* storage full: the entry just won't have its photo */ }
}

// ---- When was this photo taken? (suggests the meal and dates the diary entry) ----
// Gallery/desktop files carry it in their EXIF; the in-app camera is "now". Returns an
// ISO string: no zone for EXIF (it is the camera's local clock), UTC for everything else.
async function readTakenAt(file) {
  if (!(file instanceof File)) return new Date().toISOString(); // shot with the in-app camera
  try {
    const exif = await readExifDate(file);
    if (exif) return exif;
  } catch { /* unreadable EXIF: fall through */ }
  const age = Date.now() - file.lastModified;
  if (file.lastModified && age >= 0 && age < 120 * 86400000) return new Date(file.lastModified).toISOString();
  return new Date().toISOString();
}

async function readExifDate(file) {
  const view = new DataView(await file.slice(0, 262144).arrayBuffer());
  if (view.byteLength < 12 || view.getUint16(0) !== 0xFFD8) return null; // EXIF is read from JPEGs only
  let offset = 2;
  while (offset + 10 < view.byteLength) {
    const marker = view.getUint16(offset);
    if ((marker & 0xFF00) !== 0xFF00) return null;
    const length = view.getUint16(offset + 2);
    if (marker === 0xFFE1 && view.getUint32(offset + 4) === 0x45786966) return parseExifDate(view, offset + 10);
    offset += 2 + length;
  }
  return null;
}

function parseExifDate(view, base) {
  const little = view.getUint16(base) === 0x4949;
  const u16 = (o) => view.getUint16(o, little);
  const u32 = (o) => view.getUint32(o, little);
  const text = (entry) => {
    const count = u32(entry + 4);
    const start = count > 4 ? base + u32(entry + 8) : entry + 8;
    let out = '';
    for (let i = 0; i < count - 1 && start + i < view.byteLength; i++) out += String.fromCharCode(view.getUint8(start + i));
    return out;
  };
  const scan = (ifd, wanted) => {
    const found = {};
    const n = u16(ifd);
    for (let i = 0; i < n; i++) {
      const entry = ifd + 2 + i * 12;
      const tag = u16(entry);
      if (wanted.includes(tag)) found[tag] = tag === 0x8769 ? u32(entry + 8) : text(entry);
    }
    return found;
  };
  const ifd0 = scan(base + u32(base + 4), [0x0132, 0x8769]);
  const exif = ifd0[0x8769] ? scan(base + ifd0[0x8769], [0x9003, 0x9004]) : {};
  const raw = exif[0x9003] || exif[0x9004] || ifd0[0x0132];
  const m = /^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/.exec(raw || '');
  if (!m) return null;
  const year = Number(m[1]);
  if (year < 2000 || year > new Date().getFullYear() + 1) return null;
  return `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}`;
}
