/* Paged commercial snapshots; the API owns scope, permissions and redaction. */
window.LuriOpportunityHistory = (() => {
  const pageSize = 20;
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  const live = c => c.root?.isConnected && c.isCurrent();
  const date = (value, zone) => new Intl.DateTimeFormat("es-PE", {dateStyle:"medium", timeStyle:"short", timeZone:zone}).format(new Date(value));

  function clear(c) {
    c.commercialHistoryGeneration = (c.commercialHistoryGeneration || 0) + 1;
    c.commercialHistory = null;
    c.root?.querySelector("#commercial-editor")?.removeAttribute("aria-busy");
  }
  function markup(c, state, rows) {
    const {stages, assignees, info} = c.commercial;
    const names = Object.fromEntries(assignees.map(u => [u.id, u.name]));
    const stageNames = Object.fromEntries(stages.map(s => [s.code, s.name]));
    return `<section aria-label="Historial comercial"><h4>Historial comercial</h4>
      <p>Página ${state.page}${state.throughVersion ? ` · Hasta la versión ${state.throughVersion}` : ""}</p>
      <ol>${rows.map(h => `<li>Versión ${esc(h.version)} · ${esc(date(h.occurred_at, info.timezone))} · ${esc(h.snapshot.title)} · ${esc(stageNames[h.snapshot.stage_code] || h.snapshot.stage_code)} · Responsable ${esc(names[h.snapshot.assigned_user_id] || "Integrante del equipo")} · Modificado por ${esc(names[h.actor_user_id] || "Integrante del equipo")}<p>${esc(h.snapshot.next_action?.description || h.snapshot.close_reason || h.snapshot.no_action_reason)}</p></li>`).join("") || "<li>No hay versiones en esta página.</li>"}</ol>
      <nav class="crm-pagination" aria-label="Páginas del historial comercial">
        <button type="button" class="secondary-button" data-commercial="history-previous" ${state.page <= 1 ? "disabled" : ""}>Versiones más recientes</button>
        <span>Página ${state.page}</span>
        <button type="button" class="secondary-button" data-commercial="history-next" ${!state.hasNext ? "disabled" : ""}>Versiones anteriores</button>
      </nav>
      <button type="button" class="secondary-button" data-commercial="history-refresh">Actualizar historial</button>
      <p class="muted">Actualizar vuelve al comienzo e incluye nuevas versiones.</p>
      </section>`;
  }
  async function open(c, id, page = 1, throughVersion = null) {
    if (!live(c)) return;
    const editor = c.root.querySelector("#commercial-editor");
    if (!editor) return;
    const ticket = (c.commercialHistoryGeneration || 0) + 1;
    c.commercialHistoryGeneration = ticket;
    const current = () => live(c) && c.commercialHistoryGeneration === ticket;
    const controls = Array.from(editor.querySelectorAll("button"), node => ({node, disabled:node.disabled}));
    controls.forEach(({node}) => node.disabled = true);
    editor.setAttribute("aria-busy", "true");
    const loading = document.createElement("p");
    loading.setAttribute("role", "status"); loading.textContent = "Consultando historial…";
    editor.append(loading);
    const base = `/organizations/${c.org}/crm/opportunities/${encodeURIComponent(id)}/history`;
    try {
      const params = new URLSearchParams({page:String(page), page_size:String(pageSize)});
      if (throughVersion) params.set("through_version", String(throughVersion));
      const rows = await c.api(`${base}?${params}`);
      if (!current()) return;
      const anchor = throughVersion || rows[0]?.version || null;
      let hasNext = false;
      if (rows.length === pageSize) {
        const lookahead = new URLSearchParams({page:String(page * pageSize + 1), page_size:"1", through_version:String(anchor)});
        const next = await c.api(`${base}?${lookahead}`);
        if (!current()) return;
        hasNext = next.length > 0;
      }
      const state = {id, page, throughVersion:anchor, hasNext};
      c.commercialHistory = state;
      editor.innerHTML = markup(c, state, rows);
      c.root.querySelector("#commercial-feedback").textContent = "";
    } finally {
      loading.remove();
      if (current()) {
        editor.removeAttribute("aria-busy");
        controls.forEach(({node, disabled}) => {if (node.isConnected) node.disabled = disabled;});
      }
    }
  }
  async function navigate(c, action) {
    const state = c.commercialHistory;
    if (!state) return;
    if (action === "history-refresh") return open(c, state.id);
    if (action === "history-previous" && state.page > 1) return open(c, state.id, state.page - 1, state.throughVersion);
    if (action === "history-next" && state.hasNext) return open(c, state.id, state.page + 1, state.throughVersion);
  }
  return {open, navigate, clear};
})();
