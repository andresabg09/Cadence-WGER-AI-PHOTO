// "Pregúntale a cadence": a small chat that explains how cadence works and why the person's own numbers are what they are.
// It answers from a written knowledge base plus their data. It cannot change anything and it is not medical advice.
(function () {
  const SUGGESTIONS = [
    '¿Por qué mi meta es esta?',
    '¿Tengo que quemar calorías para ganar músculo?',
    '¿Qué tan exacto es este cálculo?',
    '¿Cuántas libras puedo bajar al mes?',
    '¿Qué pasa si registro menos de lo que como?',
  ];

  function open({ prompt } = {}) {
    const scrim = document.createElement('div');
    scrim.className = 'sheet-scrim';
    const sheet = document.createElement('div');
    sheet.className = 'entry-sheet as-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Pregúntale a cadence');
    sheet.innerHTML = `<div style="display:flex;align-items:center;justify-content:space-between;gap:10px;">
        <div><h3 class="disp" style="margin:0;">Pregúntale a cadence</h3>
        <div class="when" style="margin-top:2px;">Responde con tus números · no es consejo médico</div></div>
        <button type="button" class="ac-round" id="asClose" aria-label="Cerrar" style="width:38px;height:38px;font-size:15px;">✕</button></div>
      <div class="ac" style="margin-top:12px;">
        <div class="ac-msgs" id="asMsgs" aria-live="polite"></div>
        <div class="as-chips" id="asChips">${SUGGESTIONS.map((s) => `<button type="button">${escapeHtml(s)}</button>`).join('')}</div>
        <div class="ac-compose">
          <button type="button" class="ac-round" id="asMic" aria-label="Dictar con la voz" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M5 11a7 7 0 0014 0M12 18v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
          <textarea class="input ac-text" id="asText" rows="1" data-placeholder="Escribe o dicta tu duda…" placeholder="Escribe o dicta tu duda…" autocomplete="off" maxlength="500" enterkeyhint="send"></textarea>
          <button type="button" class="ac-round go" id="asSend" aria-label="Enviar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        </div>
        <p class="as-note">Las calorías son estimaciones. Si tienes una condición de salud, habla con tu médico o nutricionista.</p>
      </div>`;
    document.body.append(scrim, sheet);
    pushOverlay(() => { scrim.remove(); sheet.remove(); });
    scrim.addEventListener('click', () => dismissOverlay());
    sheet.querySelector('#asClose').addEventListener('click', () => dismissOverlay());

    const msgs = sheet.querySelector('#asMsgs');
    const input = sheet.querySelector('#asText');
    const note = sheet.querySelector('.as-note');
    const calm = note.textContent;
    const dict = cadenceDictation.attach({ field: input, button: sheet.querySelector('#asMic'), onState: ({ on, busy: working }) => { note.textContent = on ? 'Te escucho… toca el micrófono para dejar de escuchar. No se envía solo.' : working ? 'Pasando tu voz a texto…' : calm; }, onError: (m) => { note.textContent = m; } });
    const history = [];
    let busy = false;
    const add = (role, text) => {
      const el = document.createElement('div');
      el.className = `ac-msg ${role}`;
      el.textContent = text;
      msgs.append(el);
      msgs.scrollTop = msgs.scrollHeight;
      return el;
    };
    add('bot', 'Hola. Pregúntame cómo se calculan tus calorías, qué significa tu meta o cómo usar cadence. Te respondo con tus propios números.');

    async function ask(text) {
      const t = text.trim();
      if (!t || busy) return;
      busy = true;
      dict.stop();
      sheet.querySelector('#asChips').style.display = 'none';
      input.value = ''; cadenceDictation.grow(input);
      add('me', t);
      history.push({ role: 'user', text: t });
      const dots = document.createElement('div');
      dots.className = 'ac-typing'; dots.innerHTML = '<i></i><i></i><i></i>';
      msgs.append(dots); msgs.scrollTop = msgs.scrollHeight;
      try {
        const out = await apiPost('api/assistant', { history });
        dots.remove();
        add('bot', out.reply);
        history.push({ role: 'assistant', text: out.reply });
      } catch (err) {
        dots.remove();
        add('bot', err.message || 'No pude responder ahora. Prueba de nuevo en un momento.');
        history.pop();
      }
      busy = false;
    }
    sheet.querySelectorAll('#asChips button').forEach((b) => b.addEventListener('click', () => ask(b.textContent)));
    sheet.querySelector('#asSend').addEventListener('click', () => ask(input.value));
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input.value); } });
    if (prompt) ask(prompt); else setTimeout(() => input.focus(), 250);
  }

  window.cadenceAssistant = { open };
})();
