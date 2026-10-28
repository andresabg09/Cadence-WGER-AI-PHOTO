// Loading screen: the clean cadence mark draws itself, then the name. Shown once each time the app is opened (per session),
// it does not hold anything back (the page loads behind it) and a tap skips it. With "reduce motion" it is a still logo.
(function () {
  try {
    if (navigator.webdriver || sessionStorage.getItem('cadence_splash')) return;
    sessionStorage.setItem('cadence_splash', '1');
  } catch { return; }
  const calm = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const el = document.createElement('div');
  el.className = `splash${calm ? ' calm' : ''}`;
  el.setAttribute('aria-hidden', 'true');
  el.innerHTML = `<svg class="sp-mark" width="200" height="200" viewBox="-256 -256 512 512" style="overflow:visible">
      <defs>
        <radialGradient id="spGlowG" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="#7C5CFF" stop-opacity="0.5"/><stop offset="100%" stop-color="#7C5CFF" stop-opacity="0"/></radialGradient>
        <linearGradient id="spRingG" x1="0%" y1="100%" x2="100%" y2="0%"><stop offset="0%" stop-color="#7C5CFF"/><stop offset="100%" stop-color="#2DD4FF"/></linearGradient>
        <linearGradient id="spLensG" x1="15%" y1="0%" x2="85%" y2="100%"><stop offset="0%" stop-color="#9B82FF"/><stop offset="100%" stop-color="#1FB8E8"/></linearGradient>
      </defs>
      <circle class="sp-glow" r="330" fill="url(#spGlowG)"/>
      <circle class="sp-track" r="158" fill="none" stroke-width="34"/>
      <g class="sp-spin"><circle class="sp-arc" r="158" fill="none" stroke="url(#spRingG)" stroke-width="34" stroke-linecap="round"/></g>
      <circle class="sp-lens" r="104" fill="url(#spLensG)"/>
      <g class="sp-pupil"><circle r="62" fill="#0A0A12" fill-opacity="0.9"/><circle r="62" fill="none" stroke="#FFFFFF" stroke-opacity="0.22" stroke-width="3"/></g>
      <circle class="sp-dot" cx="-22" cy="-24" r="15" fill="#FFFFFF"/>
      <circle class="sp-dot2" cx="20" cy="22" r="6" fill="#FFFFFF"/>
      <path class="sp-spark" d="M122 -150 l9 28 28 9 -28 9 -9 28 -9 -28 -28 -9 28 -9z"/>
    </svg>
    <div class="sp-name">cadence</div>
    <div class="sp-bar"></div>`;
  document.documentElement.appendChild(el);
  const leave = () => { if (!el.isConnected) return; el.classList.add('out'); setTimeout(() => el.remove(), 360); };
  el.addEventListener('pointerdown', leave);
  setTimeout(leave, calm ? 900 : 2450);
})();
