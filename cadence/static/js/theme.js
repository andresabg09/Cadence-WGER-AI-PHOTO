// Oscuro -> Claro -> Lectura -> Sistema -> Oscuro, one tap at a time, per
// the "no desplegable" requirement. "Sistema" = no data-theme attribute at
// all, so the prefers-color-scheme media query in pulse.css decides.
const THEME_CYCLE = ['dark', 'light', 'reading', 'system'];
const STORAGE_KEY = 'cadence_theme';

const ICONS = {
  dark: '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" fill="currentColor"/>',
  light: '<circle cx="12" cy="12" r="4.5" fill="currentColor"/><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8L6 18M18 6l1.8-1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
  reading: '<path d="M4 5.5A2.5 2.5 0 016.5 3H18a1 1 0 011 1v14.5a1 1 0 01-1 1H6.5A2.5 2.5 0 014 17V5.5z" stroke="currentColor" stroke-width="1.6"/><path d="M4 17a2.5 2.5 0 012.5-2.5H19" stroke="currentColor" stroke-width="1.6"/>',
  system: '<rect x="3" y="4" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.6"/><path d="M8 21h8M12 17v4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>',
};
const LABELS = { dark: 'Oscuro', light: 'Claro', reading: 'Lectura', system: 'Sistema' };

function getStoredTheme() {
  return localStorage.getItem(STORAGE_KEY) || 'dark';
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
    const next = THEME_CYCLE[(THEME_CYCLE.indexOf(theme) + 1) % THEME_CYCLE.length];
    btn.setAttribute('aria-label', `Apariencia: ${LABELS[theme]} — toca para cambiar a ${LABELS[next]}`);
  }
}

function themeSound(theme) {
  if (!window.sfx) return;
  sfx.play({ dark: 'themeDark', light: 'themeLight', reading: 'themeReading' }[theme] || 'tick');
}

function initThemeToggle() {
  const theme = getStoredTheme();
  applyTheme(theme);
  const btn = document.getElementById('themeToggle');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const current = getStoredTheme();
    const next = THEME_CYCLE[(THEME_CYCLE.indexOf(current) + 1) % THEME_CYCLE.length];
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
    themeSound(next);
  });
}

applyTheme(getStoredTheme());
document.addEventListener('DOMContentLoaded', initThemeToggle);
