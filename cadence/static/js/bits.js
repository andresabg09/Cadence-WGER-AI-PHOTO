// Small shared drawing helpers: level bars, rings, hexagonal awards, icons, coin. Plain strings of SVG/HTML.
(function () {
  // Names used before the icon set: they map to Phosphor icons (js/icons.js). New code can use a Phosphor name directly.
  const ICONS = {
    flame: 'fire', bolt: 'lightning', fork: 'fork-knife', drop: 'drop', scale: 'scales', leaf: 'leaf', moon: 'moon', star: 'star', check: 'check',
    wheat: 'grains', dumbbell: 'barbell', shoe: 'sneaker', bike: 'person-simple-bike', swim: 'person-simple-swim', yoga: 'flower-lotus', sun: 'sun',
    camera: 'camera', x: 'x', trophy: 'trophy', heart: 'heart', home: 'house', bars: 'chart-bar', user: 'user', search: 'magnifying-glass',
  };
  let seq = 0;
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function icon(name, size = 22, color = 'currentColor') {
    return window.cadenceIcons.svg(ICONS[name] || name, size, color);
  }

  // Four-segment level bar with a marker (0-100) and a label under it. The last segment is green.
  function segBar(pct, markerText) {
    const p = Math.max(0, Math.min(100, pct));
    const segs = [0, 1, 2, 3].map((i) => {
      const part = Math.max(0, Math.min(1, (p - i * 25) / 25));
      return `<div class="seg${i === 3 ? ' last' : ''}"><i style="width:${(part * 100).toFixed(0)}%"></i></div>`;
    }).join('');
    return `<div class="seg-bar">${segs}<div class="mark" style="left:${p}%"></div><div class="mark-label" style="left:${Math.min(88, Math.max(12, p))}%">${esc(markerText)}</div></div>`;
  }

  // Ring with free HTML in the middle.
  function ring(size, pct, inner, stroke = 8, c1 = 'var(--accent-from)', c2 = 'var(--accent-to)') {
    const id = `bits-r${++seq}`;
    const r = (size - stroke) / 2;
    const circ = 2 * Math.PI * r;
    const dash = circ * Math.max(0, Math.min(100, pct)) / 100;
    return `<div style="position:relative;width:${size}px;height:${size}px;flex-shrink:0;"><svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
      <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" style="stop-color:${c1}"/><stop offset="1" style="stop-color:${c2}"/></linearGradient></defs>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="rgba(127,127,140,0.18)" stroke-width="${stroke}"/>
      <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#${id})" stroke-width="${stroke}" stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${circ.toFixed(1)}" transform="rotate(-90 ${size / 2} ${size / 2})"/></svg>
      <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;">${inner}</div></div>`;
  }

  // Hexagonal award: coloured when earned, dashed outline when still to earn.
  function hex(iconName, c1, c2, size = 56, on = true) {
    const id = `bits-h${++seq}`;
    const w = size, h = Math.round(size * 1.125);
    const body = on
      ? `<defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs>
         <path d="M32 3 L59 18.5 V53.5 L32 69 L5 53.5 V18.5 Z" fill="url(#${id})" stroke="rgba(255,255,255,0.45)" stroke-width="2" stroke-linejoin="round"/>
         <path d="M32 9 L53.5 21 V51 L32 63 L10.5 51 V21 Z" fill="none" stroke="rgba(255,255,255,0.28)" stroke-width="1.4" stroke-linejoin="round"/>`
      : '<path d="M32 3 L59 18.5 V53.5 L32 69 L5 53.5 V18.5 Z" fill="rgba(127,127,140,0.06)" stroke="rgba(127,127,140,0.45)" stroke-width="2" stroke-dasharray="3 5" stroke-linejoin="round"/>';
    const stroke = on ? '#fff' : 'rgba(127,127,140,0.7)';
    return `<svg width="${w}" height="${h}" viewBox="0 0 64 72" fill="none" aria-hidden="true">${body}${window.cadenceIcons.svg(ICONS[iconName] || iconName || 'star', 26, stroke).replace('<svg ', '<svg x="19" y="22" ')}</svg>`;
  }

  function coin(size = 18) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10.5" fill="#F5B942" stroke="#FFE08A" stroke-width="1.5"/><circle cx="12" cy="12" r="7" fill="none" stroke="#B9801A" stroke-width="1.3"/><path d="M12 7.5v9M9.5 10c0-1 1-1.6 2.5-1.6s2.5.6 2.5 1.6-1 1.5-2.5 1.8-2.5.8-2.5 1.8 1 1.6 2.5 1.6 2.5-.6 2.5-1.6" fill="none" stroke="#B9801A" stroke-width="1.2" stroke-linecap="round"/></svg>`;
  }

  // The picture of each award: [icon, colour 1, colour 2].
  const ART = {
    protein: ['dumbbell', '#7C5CFF', '#4A6BFF'], fibre: ['wheat', '#F0873A', '#FFD08A'], variety: ['leaf', '#2FB57F', '#8DF7C8'],
    balance: ['bolt', '#2DD4FF', '#4A6BFF'], water: ['drop', '#2DD4FF', '#4A6BFF'], early: ['sun', '#F5B942', '#FFE08A'],
    streak: ['flame', '#FF8A5B', '#FFD08A'], camera: ['camera', '#B27BC4', '#FF9EC0'], scale: ['scale', '#8DF7C8', '#2DD4FF'],
    trophy: ['trophy', '#F5B942', '#FF8A5B'], move: ['sneaker', '#2FB57F', '#8DF7C8'], target: ['target', '#FF6A9A', '#FFB45C'],
    fork: ['fork', '#4A6BFF', '#9B82FF'], bolt: ['bolt', '#F5B942', '#FFE08A'],
    sun: ['sun', '#F5B942', '#FFE08A'], leaf: ['leaf', '#2FB57F', '#8DF7C8'],
  };
  const award = (art, size = 56, on = true) => { const [ic, c1, c2] = ART[art] || ART.balance; return hex(ic, c1, c2, size, on); };

  window.bits = { ICONS, icon, segBar, ring, hex, coin, esc, ART, award };
})();
