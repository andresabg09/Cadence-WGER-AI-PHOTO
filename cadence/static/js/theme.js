// Oscuro -> Claro -> Lectura -> Sistema -> Oscuro, one tap at a time, per
// the "no desplegable" requirement. "Sistema" = no data-theme attribute at
// all, so the prefers-color-scheme media query in pulse.css decides.
const BASE_THEMES = ['dark', 'light', 'reading'];
// Themes bought with coins join the cycle (the server tells which ones the person owns; see rememberUser in api.js).
function themeCycle() {
  let owned = [];
  try { owned = JSON.parse(localStorage.getItem('cadence_owned_themes') || '[]'); } catch { /* no storage */ }
  return [...BASE_THEMES, ...owned.filter((t) => t in ICONS), 'system'];
}
const STORAGE_KEY = 'cadence_theme';

const ICONS = {
  dark: '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" fill="currentColor"/>',
  light: '<circle cx="12" cy="12" r="4.5" fill="currentColor"/><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8L6 18M18 6l1.8-1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  reading: '<path d="M4 5.5A2.5 2.5 0 016.5 3H18a1 1 0 011 1v14.5a1 1 0 01-1 1H6.5A2.5 2.5 0 014 17V5.5z" stroke="currentColor" stroke-width="1.6"/><path d="M4 17a2.5 2.5 0 012.5-2.5H19" stroke="currentColor" stroke-width="1.6"/>',
  aurora: '<path d="M12 3l2.4 5.2 5.6.7-4.1 3.9 1 5.6L12 15.6 7.1 18.4l1-5.6L4 8.9l5.6-.7L12 3z" fill="currentColor"/>',
  atardecer: '<path d="M4 17h16M7 17a5 5 0 0110 0M12 5v2M5 9l1.4 1.4M19 9l-1.4 1.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/>',
  oceano: '<path d="M3 15c2 0 2-1.5 4.5-1.5S9.5 15 12 15s2.5-1.5 4.5-1.5S19 15 21 15M3 19c2 0 2-1.5 4.5-1.5S9.5 19 12 19s2.5-1.5 4.5-1.5S19 19 21 19M12 4c2.5 3 3.5 5 3.5 6.5a3.5 3.5 0 01-7 0C8.5 9 9.5 7 12 4z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
  system: '<rect x="3" y="4" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
};
const LABELS = { dark: 'Oscuro', light: 'Claro', reading: 'Lectura', aurora: 'Aurora', atardecer: 'Atardecer', oceano: 'Océano', system: 'Sistema' };

function getStoredTheme() {
  const stored = localStorage.getItem(STORAGE_KEY) || 'dark';
  return themeCycle().includes(stored) ? stored : 'dark'; // a theme the person no longer has falls back to dark
}

function applyTheme(theme) {
  if (theme === 'system') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', theme);
  }
  const btn = document.getElementById('themeToggle');
  if (btn) {
    const svg = btn.querySelector('svg');
    if (svg) svg.innerHTML = ICONS[theme];
    const cycle = themeCycle();
    const next = cycle[(cycle.indexOf(theme) + 1) % cycle.length];
    btn.setAttribute('aria-label', `Apariencia: ${LABELS[theme]} — toca para cambiar a ${LABELS[next]}`);
  }
}

function themeSound(theme) {
  if (!window.sfx) return;
  sfx.play({ dark: 'themeDark', light: 'themeLight', reading: 'themeReading', aurora: 'themeLight', atardecer: 'themeReading', oceano: 'themeDark' }[theme] || 'tick');
}

function initThemeToggle() {
  const theme = getStoredTheme();
  applyTheme(theme);
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const current = getStoredTheme();
    const cycle = themeCycle();
    const next = cycle[(cycle.indexOf(current) + 1) % cycle.length];
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
    themeSound(next);
  });
}

applyTheme(getStoredTheme());
document.addEventListener('DOMContentLoaded', initThemeToggle);
