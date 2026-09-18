/* Conversation UI. Authorization and delivery policy remain server enforced. */
window.LuriConversations = (() => {
  let context = null;
  const labels = {open: "Abierta", closed: "Cerrada", archived: "Archivada", bot_active: "Atiende Luri", waiting_human: "Esperando atención humana", human_active: "Atención humana activa", resolved: "Atención resuelta", received: "Recibido", processed: "Procesado", pending: "Pendiente de envío", sent: "Enviado al proveedor", delivered: "Entregado", read: "Leído", failed: "Envío fallido"};
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  const date = value => value ? new Intl.DateTimeFormat("es-PE", {dateStyle:"medium", timeStyle:"short"}).format(new Date(value)) : "—";
  const label = value => labels[value] || value;
  const live = c => context === c && c.root?.isConnected;
  const can = (c, permission) => c.permissions.includes(permission);
  const button = (action, text, disabled = false) => `<button type="button" class="secondary-button" data-conversation-action="${action}" ${disabled ? "disabled" : ""}>${esc(text)}</button>`;
  const errorText = error => error.status === 403 ? "No tienes permiso para esta acción." : error.status === 409 ? "El estado cambió o la atención no está disponible. Actualiza la conversación." : error.status === 404 ? "El registro ya no está disponible." : "No se pudo completar la operación. Actualiza o intenta nuevamente.";

  function reset() { context = null; }
  async function render(org, api, user, permissions) {
    const c = {org, api, user, permissions, page:1, messagePage:1, selected:null, root:null, busy:false, draft:""};
    context = c;
    c.list = await api(`/organizations/${org}/conversations?page=1&page_size=20`);
    return listMarkup(c);
  }
  function listMarkup(c) {
    return `<div class="view-heading"><div><h3>Conversaciones</h3><p>${c.list.total} conversaciones de tu empresa.</p></div></div>
      <article class="panel"><div class="conversation-list">${c.list.items.map(item => `<button type="button" class="conversation-row" data-conversation-id="${esc(item.id)}"><strong>${esc(item.masked_customer_identifier)}</strong><span>${esc(label(item.status))} · ${item.message_count} mensajes</span><span>${esc(date(item.last_message_at))}</span><span>Abrir conversación →</span></button>`).join("") || '<p class="empty">Aún no hay conversaciones.</p>'}</div>
      <nav class="crm-pagination" aria-label="Páginas de conversaciones">${button("previous", "Anterior", !c.list.has_previous)}<span>Página ${c.page}</span>${button("next", "Siguiente", !c.list.has_next)}</nav></article>`;
  }
  async function loadDetail(c) {
    const path = `/organizations/${c.org}/conversations/${c.selected}`;
    const [detail, messages, handoff] = await Promise.all([
      c.api(path),
      can(c, "conversation.read_content") ? c.api(`${path}/messages?page=${c.messagePage}&page_size=50`) : null,
      can(c, "handoff.read") ? c.api(`${path}/handoff`).catch(error => {if (error.status === 404) return null; throw error;}) : null,
    ]);
    if (!live(c)) return;
    c.detail = detail; c.messages = messages; c.handoff = handoff;
    c.root.innerHTML = detailMarkup(c);
  }
  function detailMarkup(c) {
    const h = c.handoff;
    const active = h && ["waiting_human", "human_active"].includes(h.status);
    const own = h?.assigned_user_id === c.user.id;
    const privileged = ["platform_admin", "organization_owner", "organization_admin"].includes(c.user.role);
    const reply = can(c, "handoff.reply") && h?.status === "human_active" && (own || privileged);
    const controls = [];
    if (!active && can(c, "handoff.request") && can(c, "handoff.read")) controls.push(button("request", "Solicitar atención humana"));
    if (h?.status === "waiting_human" && !h.assigned_user_id && can(c, "handoff.claim")) controls.push(button("claim", "Tomar atención"));
    if (active && (own || privileged)) {
      if (can(c, "handoff.release") && h.status === "human_active") controls.push(button("release", "Dejar en espera"));
      if (can(c, "handoff.resolve")) controls.push(button("return-to-bot", "Devolver a Luri"), button("resolve", "Resolver atención"));
    }
    return `${button("back", "← Conversaciones")}<div class="view-heading"><div><h3>Conversación ${esc(c.detail.masked_customer_identifier)}</h3><p>${esc(label(c.detail.status))} · ${c.detail.message_count} mensajes</p></div>${button("refresh", "Actualizar")}</div>
      <p class="form-error" role="alert" id="conversation-error"></p><p role="status" id="conversation-feedback"></p>
      <section class="panel"><h4>Atención</h4><p>${can(c, "handoff.read") ? esc(label(h?.status || "bot_active")) : "Sin permiso para consultar la atención."}${h?.assigned_user_id ? (own ? " · Asignada a ti" : " · Asignada a otro integrante") : ""}</p><div class="conversation-actions">${controls.join("")}</div></section>
      <section class="panel conversation-history"><h4>Historial</h4>${c.messages ? `<ol class="conversation-messages">${c.messages.items.map(m => `<li class="conversation-message ${m.direction === "inbound" ? "inbound" : "outbound"}"><strong>${m.direction === "inbound" ? "Cliente" : "Luri / equipo"}</strong><p>${esc(m.text ?? `[${m.message_type}: contenido no disponible]`)}</p><small>${esc(date(m.occurred_at))} · ${esc(label(m.status))}</small></li>`).join("") || '<li class="empty">Sin mensajes registrados.</li>'}</ol><nav class="crm-pagination" aria-label="Páginas del historial">${button("older", "Página anterior", !c.messages.has_previous)}<span>Página ${c.messagePage}</span>${button("newer", "Página siguiente", !c.messages.has_next)}</nav>` : '<p>No tienes permiso para leer el contenido de los mensajes.</p>'}</section>
      ${reply ? `<form id="conversation-reply" class="panel"><label for="conversation-text">Respuesta humana</label><textarea id="conversation-text" rows="4" maxlength="4096" required>${esc(c.draft)}</textarea><p class="muted">Se enviará por WhatsApp al cliente de esta conversación.</p><button type="submit" class="primary-button">Enviar respuesta</button></form>` : '<p class="muted">Para responder necesitas una atención activa y los permisos correspondientes.</p>'}`;
  }
  function showError(c, message) {
    if (!live(c)) return;
    let target = c.root.querySelector("#conversation-error");
    if (!target) { target = document.createElement("p"); target.id = "conversation-error"; target.setAttribute("role", "alert"); c.root.prepend(target); }
    target.textContent = message;
  }
  async function action(c, name, id) {
    if (!live(c) || c.busy) return;
    c.draft = c.root.querySelector("#conversation-text")?.value ?? c.draft;
    c.busy = true;
    const previous = {page:c.page, messagePage:c.messagePage, selected:c.selected};
    c.root.querySelectorAll("button").forEach(b => { b.dataset.wasDisabled = String(b.disabled); b.disabled = true; });
    try {
      if (id) { c.selected = id; c.messagePage = 1; c.draft = ""; }
      else if (name === "back") { c.selected = null; c.draft = ""; }
      else if (name === "previous") c.page--;
      else if (name === "next") c.page++;
      else if (name === "older") c.messagePage--;
      else if (name === "newer") c.messagePage++;
      else if (["request", "claim", "release", "return-to-bot", "resolve"].includes(name)) {
        await c.api(`/organizations/${c.org}/conversations/${c.selected}/handoff/${name}`, {method:"POST", ...(name === "request" ? {body:JSON.stringify({reason_code:"operator_request"})} : {})});
      }
      if (!live(c)) return;
      if (c.selected) await loadDetail(c);
      else {
        const list = await c.api(`/organizations/${c.org}/conversations?page=${c.page}&page_size=20`);
        if (live(c)) { c.list = list; c.root.innerHTML = listMarkup(c); }
      }
    } catch (error) { Object.assign(c, previous); showError(c, errorText(error)); }
    finally {
      c.busy = false;
      if (live(c)) c.root.querySelectorAll("button[data-was-disabled]").forEach(b => {b.disabled = b.dataset.wasDisabled === "true"; delete b.dataset.wasDisabled;});
    }
  }
  async function send(c, event) {
    event.preventDefault();
    if (!live(c) || c.busy) return;
    const text = c.root.querySelector("#conversation-text").value.trim();
    if (!text) return;
    c.draft = text; c.busy = true;
    const form = event.target;
    form.querySelectorAll("button, textarea").forEach(e => e.disabled = true);
    // Store only a content fingerprint and key, never the message or credentials.
    const storage = `luri.reply.${c.user.id}.${c.org}.${c.selected}`;
    let submitted = false;
    let confirmed = false;
    try {
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
      const hash = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, "0")).join("");
      const saved = JSON.parse(sessionStorage.getItem(storage) || "null");
      const key = saved?.hash === hash ? saved.key : crypto.randomUUID();
      sessionStorage.setItem(storage, JSON.stringify({hash, key}));
      if (!live(c)) return;
      submitted = true;
      const result = await c.api(`/organizations/${c.org}/conversations/${c.selected}/handoff/messages`, {method:"POST", body:JSON.stringify({text, idempotency_key:key})});
      if (result.status === "sent" || result.status === "delivered" || result.status === "read") {
        confirmed = true; sessionStorage.removeItem(storage); c.draft = "";
        form.querySelector("textarea").value = "";
      }
      if (!live(c)) return;
      await loadDetail(c);
      if (live(c)) c.root.querySelector("#conversation-feedback").textContent = `Estado de la respuesta: ${label(result.status)}.${result.status === "pending" ? " Actualiza el historial para comprobar el resultado." : ""}`;
    } catch (error) {
      showError(c, confirmed ? "La respuesta fue enviada al proveedor, pero no se pudo actualizar el historial. Pulsa Actualizar; no es necesario reenviarla." : submitted ? "No se pudo confirmar el resultado. Revisa el historial antes de volver a enviar. Si reintentas el mismo texto se reutilizará su identificador para evitar duplicados." : errorText(error));
    } finally { c.busy = false; if (live(c)) form.querySelectorAll("button, textarea").forEach(e => e.disabled = false); }
  }
  function mount(root) {
    const c = context; if (!c) return;
    c.root = root;
    // Abort old handlers because the portal reuses the same content element.
    root._conversationEvents?.abort();
    const events = new AbortController(); root._conversationEvents = events;
    root.addEventListener("click", event => {
      const target = event.target.closest("[data-conversation-action], [data-conversation-id]");
      if (target && root.contains(target)) action(c, target.dataset.conversationAction, target.dataset.conversationId);
    }, {signal:events.signal});
    root.addEventListener("submit", event => {if (event.target.id === "conversation-reply") send(c, event);}, {signal:events.signal});
  }
  return {render, mount, reset};
})();
