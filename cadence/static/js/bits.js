// Small shared drawing helpers: level bars, rings, hexagonal awards, icons, coin. Plain strings of SVG/HTML.
(function () {
  const ICONS = {
    flame: 'M12 3c1 3 4 4.5 4 8.5a4 4 0 01-8 0c0-1.6.6-2.6 1.4-3.6.2 1 .8 1.6 1.4 1.8C10.4 7.6 11 5 12 3z',
    bolt: 'M13 3L5 13h6l-1 8 8-10h-6l1-8z',
    fork: 'M6 3v6a2 2 0 002 2v10M4 3v4M8 3v4M17 21V3c-2 1.5-3 4-3 7 0 2 1.2 3 3 3',
    drop: 'M12 3s6 6.5 6 11a6 6 0 01-12 0c0-4.5 6-11 6-11z',
    scale: 'M6 4h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6a2 2 0 012-2zM8 9a4 3.4 0 018 0M12 12.5l2-2.2',
    leaf: 'M5 19c0-8 5-13 14-14 0 9-5 14-13 14M5 19c3-4 6-6 9-8',
    moon: 'M20 14A8 8 0 1110 4a6.5 6.5 0 0010 10z',
    star: 'M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z',
    check: 'M5 12.5l4.5 4.5L19 7.5',
    wheat: 'M12 21V9M12 9c-2.5 0-4-1.5-4-4 2.5 0 4 1.5 4 4zM12 9c2.5 0 4-1.5 4-4-2.5 0-4 1.5-4 4zM12 15c-2.5 0-4-1.5-4-4 2.5 0 4 1.5 4 4zM12 15c2.5 0 4-1.5 4-4-2.5 0-4 1.5-4 4z',
    dumbbell: 'M6.5 7v10M17.5 7v10M3.5 9.5v5M20.5 9.5v5M6.5 12h11',
    shoe: 'M3 17c0-2 1-3 3-3l3-6 3 3 4 1c3 .5 5 1.5 5 4v1H3z',
    bike: 'M6 18a3 3 0 100-.01M18 18a3 3 0 100-.01M6 18l4-7h6l2 7M10 11l3 7',
    swim: 'M3 17c2 0 2-1.5 4.5-1.5S10 17 12 17s2.5-1.5 4.5-1.5S19 17 21 17M8 11a2 2 0 104 0M12 11l3 2 3-1',
    yoga: 'M12 5a1.7 1.7 0 100 .01M5 20l4-6 3 2 3-2 4 6M12 8v5',
    sun: 'M12 8a4 4 0 100 8 4 4 0 000-8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5',
    camera: 'M4 8h3l1.5-2h7L17 8h3v11H4V8zM12 17a3.5 3.5 0 100-7 3.5 3.5 0 000 7z',
    x: 'M6 6l12 12M18 6L6 18',
    trophy: 'M8 4h8v5a4 4 0 01-8 0V4zM8 6H5v1.5A3 3 0 008 10.5M16 6h3v1.5a3 3 0 01-3 3M12 13v4M9 20h6',
    heart: 'M12 20s-7-4.4-7-10a4 4 0 017-2.6A4 4 0 0119 10c0 5.6-7 10-7 10z',
    home: 'M4 11l8-7 8 7v8a1 1 0 01-1 1h-4v-6H9v6H5a1 1 0 01-1-1v-8z',
    bars: 'M6 20V11M12 20V5M18 20v-6',
    user: 'M12 4a3.6 3.6 0 100 7.2A3.6 3.6 0 0012 4zM5 20c1.4-3.8 4.2-5.6 7-5.6s5.6 1.8 7 5.6',
  };
  let seq = 0;
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function icon(name, size = 22, color = 'currentColor', sw = 1.9) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${color}" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${ICONS[name] || ICONS.star}"/></svg>`;
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
    return `<svg width="${w}" height="${h}" viewBox="0 0 64 72" fill="none" aria-hidden="true">${body}<g transform="translate(20 24)" stroke="${stroke}" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" fill="none"><path d="${ICONS[iconName] || ICONS.star}"/></g></svg>`;
  }

  function coin(size = 18) {
    return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10.5" fill="#F5B942" stroke="#FFE08A" stroke-width="1.5"/><circle cx="12" cy="12" r="7" fill="none" stroke="#B9801A" stroke-width="1.3"/><path d="M12 7.5v9M9.5 10c0-1 1-1.6 2.5-1.6s2.5.6 2.5 1.6-1 1.5-2.5 1.8-2.5.8-2.5 1.8 1 1.6 2.5 1.6 2.5-.6 2.5-1.6" fill="none" stroke="#B9801A" stroke-width="1.2" stroke-linecap="round"/></svg>`;
  }

  // The picture of each award: [icon, colour 1, colour 2].
  const ART = {
    protein: ['dumbbell', '#7C5CFF', '#4A6BFF'], fibre: ['wheat', '#F0873A', '#FFD08A'], variety: ['leaf', '#2FB57F', '#8DF7C8'],
    balance: ['bolt', '#2DD4FF', '#4A6BFF'], water: ['drop', '#2DD4FF', '#4A6BFF'], early: ['sun', '#F5B942', '#FFE08A'],
    streak: ['flame', '#FF8A5B', '#FFD08A'], camera: ['camera', '#B27BC4', '#FF9EC0'], scale: ['scale', '#8DF7C8', '#2DD4FF'],
    trophy: ['trophy', '#F5B942', '#FF8A5B'], move: ['shoe', '#2FB57F', '#8DF7C8'], target: ['star', '#FF6A9A', '#FFB45C'],
    fork: ['fork', '#4A6BFF', '#9B82FF'], bolt: ['bolt', '#F5B942', '#FFE08A'],
    sun: ['sun', '#F5B942', '#FFE08A'], leaf: ['leaf', '#2FB57F', '#8DF7C8'],
  };
  const award = (art, size = 56, on = true) => { const [ic, c1, c2] = ART[art] || ART.balance; return hex(ic, c1, c2, size, on); };

  window.bits = { ICONS, icon, segBar, ring, hex, coin, esc, ART, award };
})();
