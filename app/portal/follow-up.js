/* Commercial queue reuses the opportunity editor and customer ficha. */
window.LuriFollowUp = (() => {
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  const initial = () => ({due:"today", stage_code:"", assigned_user_id:"", page:1});
  let filters = initial(), generation = 0, current;
  function reset() { close(); filters = initial(); }
  function close() { generation++; current?.controller?.abort(); current = null; }
  async function render(org, api, user, permissions, refresh) {
    const ticket = ++generation;
    if (!permissions.includes("crm.opportunities.read") || !permissions.includes("contacts.read")) return '<p class="empty">No tienes permiso para consultar el seguimiento comercial.</p>';
    const query = new URLSearchParams({due:filters.due, page:String(filters.page), page_size:"20"});
    if (filters.stage_code) query.set("stage_code", filters.stage_code);
    if (filters.assigned_user_id) query.set("assigned_user_id", filters.assigned_user_id);
    const base = `/organizations/${org}/crm`;
    const [result, stages, assignees] = await Promise.all([
      api(`${base}/follow-up?${query}`), api(`${base}/stages`), api(`${base}/assignees`),
    ]);
    if (ticket !== generation) return "";
    const names = Object.fromEntries(assignees.map(u=>[u.id,u.name]));
    const stageNames = Object.fromEntries(stages.map(s=>[s.code,s.name]));
    const format = value => value ? new Intl.DateTimeFormat("es-PE", {dateStyle:"medium",timeStyle:"short",timeZone:result.timezone}).format(new Date(value)) : "Sin fecha";
    const canWrite = permissions.includes("crm.opportunities.write") && permissions.includes("crm.opportunities.read_content");
    current = {org, api, user, permissions, refresh, ticket, result, selected:null,
      commercial:{info:{timezone:result.timezone, can_write:canWrite}, stages, assignees},
      isCurrent:()=>ticket===generation};
    const option = (value, label, selected) => `<option value="${esc(value)}" ${value===selected?'selected':''}>${esc(label)}</option>`;
    return `<div class="view-heading"><div><h3>Agenda comercial</h3><p>Acciones de hoy, vencidas y próximas. Fechas en ${esc(result.timezone)}.</p></div><button class="secondary-button" data-follow-up="refresh">Actualizar</button></div>
      <div class="metric-grid">
      ${[["today","today","Acciones de hoy"],["overdue","overdue","Acciones vencidas"],["future","future","Próximas acciones"],["without_action","without_action","Sin acción programada"],["all","open","Abiertas"]].map(([key,count,label])=>`<article class="metric-card"><span>${label}</span><strong>${result.summary[count] ?? 0}</strong><button class="crm-link" data-follow-up="bucket" data-due="${key}">Ver ${label.toLowerCase()}</button></article>`).join("")}</div>
      <section class="panel"><form id="follow-up-filters" class="crm-filters">
      <label>Seguimiento<select name="due">${[["today","Acciones de hoy"],["overdue","Acciones vencidas"],["future","Próximas acciones (desde mañana)"],["without_action","Sin acción programada"],["all","Todas las abiertas"],["upcoming","Pendientes desde ahora"]].map(([v,t])=>option(v,t,filters.due)).join("")}</select></label>
      <label>Etapa<select name="stage_code">${option("","Todas las abiertas",filters.stage_code)}${stages.filter(s=>s.kind==="open").map(s=>option(s.code,s.name,filters.stage_code)).join("")}</select></label>
      <label>Responsable<select name="assigned_user_id">${option("","Todo el equipo",filters.assigned_user_id)}${assignees.map(u=>option(u.id,u.name,filters.assigned_user_id)).join("")}</select></label><button class="secondary-button">Aplicar filtros</button></form>
      <p>Referencia: ${esc(format(result.as_of))}. Hoy usa el día de la empresa e incluye acciones ya vencidas de hoy. Vencidas compara con esta hora; próximas empieza mañana. Los contadores respetan etapa y responsable. Actualiza para recalcular.</p>
      <ul class="commercial-list">${result.items.map(item=>{
        const overdue = item.next_action && new Date(item.next_action.due_at)<new Date(result.as_of);
        return `<li><strong>${esc(item.title)}</strong> · ${esc(stageNames[item.stage_code] || item.stage_code)}
        <p>Responsable: ${esc(names[item.assigned_user_id] || "Integrante del equipo")}</p>
        <p>${overdue ? '<strong>Acción vencida</strong> · ' : ""}${esc(item.next_action?.description || item.no_action_reason || "Sin acción programada")} · ${esc(format(item.next_action?.due_at))}</p>
        <button class="secondary-button" data-follow-up="contact" data-id="${esc(item.contact_id)}">Abrir ficha del cliente</button>
        ${canWrite ? `<button class="secondary-button" data-commercial="edit" data-opportunity="${esc(item.id)}">Editar oportunidad</button>` : ""}
        <button class="secondary-button" data-commercial="history" data-opportunity="${esc(item.id)}">Ver historial</button></li>`;
      }).join("") || '<li>No hay oportunidades con estos filtros.</li>'}</ul>
      <nav class="crm-pagination" aria-label="Seguimiento comercial"><button data-follow-up="previous" ${result.page<=1?'disabled':''}>Anterior</button><span>Página ${result.page} · ${result.total} oportunidades</span><button data-follow-up="next" ${!result.has_next?'disabled':''}>Siguiente</button></nav>
      <div id="commercial-editor"></div><p id="commercial-feedback" role="status"></p></section>`;
  }
  function mount(root) {
    const c = current;
    if (!c || !c.isCurrent()) return;
    c.root = root;
    c.controller = new AbortController();
    const listenerOptions = {signal:c.controller.signal};
    root.querySelector('#follow-up-filters').addEventListener('submit', event=>{
      event.preventDefault(); const data=new FormData(event.target);
      filters={due:data.get('due'),stage_code:data.get('stage_code'),assigned_user_id:data.get('assigned_user_id'),page:1}; c.refresh();
    },listenerOptions);
    root.addEventListener('click', async event=>{
      if (!c.isCurrent() || c.busy) return;
      const commercial=event.target.closest('[data-commercial]');
      if (commercial) return window.LuriOpportunities.action(c,commercial.dataset.commercial,commercial.dataset.opportunity,c.refresh);
      const target=event.target.closest('[data-follow-up]'); if(!target)return;
      const action=target.dataset.followUp;
      if(action==='bucket'){filters.due=target.dataset.due;filters.page=1;return c.refresh();}
      if(action==='previous'||action==='next'){filters.page+=action==='next'?1:-1;return c.refresh();}
      if(action==='refresh')return c.refresh();
      if(action==='contact'){
        c.busy=true;
        try { await window.LuriCRM.openFromConversation(c.org,c.api,target.dataset.id,c.refresh); }
        catch(error){if(c.isCurrent())root.querySelector('#commercial-feedback').textContent=error.message;}
        finally {c.busy=false;}
      }
    },listenerOptions);
    root.addEventListener('submit', event=>{
      if(event.target.id==='commercial-form')window.LuriOpportunities.submit(c,event,c.refresh);
    },listenerOptions);
  }
  return {render,mount,reset,close};
})();
