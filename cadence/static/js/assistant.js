// "Pregúntale a cadence": a chat that explains how cadence works and why the person's own numbers are what they are.
// It answers from a written knowledge base plus their data (what they ate today, their goal, weight...). It cannot change
// anything and it is not medical advice. Every person keeps their own conversations: a new chat, the list of earlier ones, delete.
(function () {
  const SUGGESTIONS = [
    '¿Cuántas calorías llevo hoy?',
    '¿Por qué mi meta es esta?',
    '¿Tengo que quemar calorías para ganar músculo?',
    '¿Qué tan exacto es este cálculo?',
    '¿Cuántas libras puedo bajar al mes?',
    '¿Qué pasa si registro menos de lo que como?',
  ];
  const GREETING = 'Hola. Veo lo que has registrado hoy y esta semana, tu agua, tus entrenos y tu peso. Pregúntame cuántas calorías llevas, por qué tu meta es la que es o cómo usar cadence.';

  const ico = (name) => `<i data-ico="${name}"></i>`;

  // "Hoy 14:20", "Ayer", "12 oct": when a chat was last used, in the person's own clock.
  function when(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(new Date()) - day(d)) / 86400000);
    if (diff === 0) return `Hoy ${d.toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' })}`;
    if (diff === 1) return 'Ayer';
    return d.toLocaleDateString('es', { day: 'numeric', month: 'short' });
  }

  function open({ prompt } = {}) {
    const scrim = document.createElement('div');
    scrim.className = 'sheet-scrim';
    const sheet = document.createElement('div');
    sheet.className = 'entry-sheet as-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-label', 'Pregúntale a cadence');
    sheet.innerHTML = `<div class="as-head">
        <div class="as-title"><h3 class="disp" id="asTitle" style="margin:0;">Pregúntale a cadence</h3>
        <div class="when" id="asSub" style="margin-top:2px;">Responde con tus números · no es consejo médico</div></div>
        <div class="as-tools">
          <button type="button" class="ac-round as-tool" id="asBack" aria-label="Volver al chat" style="display:none;">${ico('caret-left')}</button>
          <button type="button" class="ac-round as-tool" id="asHistory" aria-label="Mis chats anteriores">${ico('clock-counter-clockwise')}</button>
          <button type="button" class="ac-round as-tool" id="asNew" aria-label="Nuevo chat">${ico('note-pencil')}</button>
          <button type="button" class="ac-round as-tool" id="asClose" aria-label="Cerrar">${ico('x')}</button>
        </div></div>
      <div class="ac" id="asChat" style="margin-top:12px;">
        <div class="ac-msgs" id="asMsgs" aria-live="polite"></div>
        <div class="as-chips" id="asChips">${SUGGESTIONS.map((s) => `<button type="button">${escapeHtml(s)}</button>`).join('')}</div>
        <div class="ac-compose">
          <button type="button" class="ac-round" id="asMic" aria-label="Dictar con la voz" aria-pressed="false"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M5 11a7 7 0 0014 0M12 18v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></button>
          <textarea class="input ac-text" id="asText" rows="1" data-placeholder="Escribe o dicta tu duda…" placeholder="Escribe o dicta tu duda…" autocomplete="off" maxlength="500" enterkeyhint="send"></textarea>
          <button type="button" class="ac-round go" id="asSend" aria-label="Enviar"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        </div>
        <p class="as-note">Las calorías son estimaciones. Si tienes una condición de salud, habla con tu médico o nutricionista.</p>
      </div>
      <div class="as-history" id="asList" style="display:none;"></div>`;
    document.body.append(scrim, sheet);
    pushOverlay(() => { scrim.remove(); sheet.remove(); });
    scrim.addEventListener('click', () => dismissOverlay());
    sheet.querySelector('#asClose').addEventListener('click', () => dismissOverlay());

    const $ = (id) => sheet.querySelector(`#${id}`);
    const msgs = $('asMsgs');
    const input = $('asText');
    const note = sheet.querySelector('.as-note');
    const calm = note.textContent;
    const dict = cadenceDictation.attach({ field: input, button: $('asMic'), onHint: (t) => { note.textContent = t || calm; }, onError: (t) => { note.textContent = t; } });
    let chatId = null; // the conversation being written (null = a new one, created by the first message)
    let busy = false;

    const add = (role, text) => {
      const el = document.createElement('div');
      el.className = `ac-msg ${role}`;
      el.textContent = text;
      msgs.append(el);
      msgs.scrollTop = msgs.scrollHeight;
      return el;
    };

    function showChat() {
      $('asChat').style.display = '';
      $('asList').style.display = 'none';
      $('asBack').style.display = 'none';
      $('asHistory').style.display = '';
      $('asNew').style.display = '';
      $('asTitle').textContent = 'Pregúntale a cadence';
      $('asSub').textContent = 'Responde con tus números · no es consejo médico';
    }

    function newChat() {
      if (busy) return;
      dict.stop();
      chatId = null;
      msgs.innerHTML = '';
      add('bot', GREETING);
      $('asChips').style.display = '';
      input.value = ''; cadenceDictation.grow(input);
      showChat();
    }

    async function openChat(id) {
      try {
        const chat = await apiGet(`api/chats/${id}`);
        chatId = chat.id;
        msgs.innerHTML = '';
        chat.messages.forEach((m) => add(m.role === 'user' ? 'me' : 'bot', m.text));
        $('asChips').style.display = 'none';
        showChat();
        msgs.scrollTop = msgs.scrollHeight;
        input.focus();
      } catch (err) {
        showToast(err.message || 'No pude abrir ese chat');
      }
    }

    async function showHistory() {
      if (busy) return;
      dict.stop();
      $('asChat').style.display = 'none';
      $('asList').style.display = '';
      $('asBack').style.display = '';
      $('asHistory').style.display = 'none';
      $('asNew').style.display = 'none';
      $('asTitle').textContent = 'Mis chats';
      $('asSub').textContent = 'Solo tú los ves';
      const box = $('asList');
      box.innerHTML = '<div class="as-empty">Cargando…</div>';
      let chats;
      try {
        chats = await apiGet('api/chats');
      } catch (err) {
        box.innerHTML = `<div class="as-empty">No pude cargar tus chats: ${escapeHtml(err.message)}</div>`;
        return;
      }
      draw(chats);

      function draw(list) {
        box.innerHTML = `<button type="button" class="ac-ask" id="asNewFromList">Nuevo chat</button>`
          + (list.length ? `<div class="as-rows">${list.map((c) => `
            <div class="as-row" data-id="${c.id}">
              <button type="button" class="as-open"><b>${escapeHtml(c.title)}</b><small>${when(c.updated_at)} · ${Math.ceil(c.messages / 2)} ${Math.ceil(c.messages / 2) === 1 ? 'pregunta' : 'preguntas'}</small></button>
              <button type="button" class="as-del" aria-label="Borrar este chat">${ico('trash')}</button>
            </div>`).join('')}</div>`
            : '<div class="as-empty">Todavía no tienes chats. Escribe tu primera pregunta y quedará guardada aquí.</div>');
        box.querySelector('#asNewFromList').addEventListener('click', () => newChat());
        box.querySelectorAll('.as-row').forEach((row) => {
          const id = Number(row.dataset.id);
          row.querySelector('.as-open').addEventListener('click', () => openChat(id));
          row.querySelector('.as-del').addEventListener('click', () => {
            // Two taps: the first asks, the second deletes (no browser pop-up).
            row.innerHTML = `<span class="as-ask">¿Borrar este chat?</span><button type="button" class="btn-quiet as-no">No</button><button type="button" class="btn-quiet as-yes" style="color:var(--bad);">Borrar</button>`;
            row.querySelector('.as-no').addEventListener('click', () => draw(list));
            row.querySelector('.as-yes').addEventListener('click', async () => {
              try {
                await apiDelete(`api/chats/${id}`);
                if (chatId === id) { chatId = null; msgs.innerHTML = ''; add('bot', GREETING); $('asChips').style.display = ''; }
                draw(list.filter((c) => c.id !== id));
              } catch (err) {
                showToast(err.message || 'No pude borrar el chat');
                draw(list);
              }
            });
          });
        });
      }
    }

    async function ask(text) {
      const t = text.trim();
      if (!t || busy) return;
      busy = true;
      dict.stop();
      $('asChips').style.display = 'none';
      input.value = ''; cadenceDictation.grow(input);
      add('me', t);
      const dots = document.createElement('div');
      dots.className = 'ac-typing'; dots.innerHTML = '<i></i><i></i><i></i>';
      msgs.append(dots); msgs.scrollTop = msgs.scrollHeight;
      try {
        const out = await apiPost('api/assistant', { history: [{ role: 'user', text: t }], chat_id: chatId });
        dots.remove();
        chatId = out.chat_id;
        add('bot', out.reply);
      } catch (err) {
        dots.remove();
        add('bot', err.message || 'No pude responder ahora. Prueba de nuevo en un momento.');
      }
      busy = false;
    }

    add('bot', GREETING);
    $('asHistory').addEventListener('click', showHistory);
    $('asBack').addEventListener('click', showChat);
    $('asNew').addEventListener('click', newChat);
    sheet.querySelectorAll('#asChips button').forEach((b) => b.addEventListener('click', () => ask(b.textContent)));
    $('asSend').addEventListener('click', () => ask(input.value));
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(input.value); } });
    if (prompt) ask(prompt); else setTimeout(() => input.focus(), 250);
  }

  window.cadenceAssistant = { open };
})();
