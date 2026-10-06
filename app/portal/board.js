/* Stage columns use the existing scoped, paginated opportunity API and editor. */
window.LuriBoard = (() => {
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  let generation = 0, current, assignee = "", pages = {};
  function close() { generation++; current?.controller?.abort(); current = null; }
  function reset() { close(); assignee = ""; pages = {}; }
  async function render(org, api, user, permissions, refresh) {
    const ticket = ++generation;
    if (!permissions.includes("crm.opportunities.read") || !permissions.includes("contacts.read")) return '<p class="empty">No tienes permiso para consultar el tablero comercial.</p>';
    const base = `/organizations/${org}/crm`;
    const [stages, assignees, clock] = await Promise.all([api(`${base}/stages`), api(`${base}/assignees`), api(`${base}/follow-up?page_size=1`)]);
    if (ticket !== generation) return "";
    const columns = await Promise.all(stages.map(async stage => {
      const query = new URLSearchParams({stage_code:stage.code, page:String(pages[stage.code] || 1), page_size:"10"});
      if (assignee) query.set("assigned_user_id",assignee);
      return {stage, result:await api(`${base}/opportunities?${query}`)};
    }));
    if (ticket !== generation) return "";
    const canWrite = permissions.includes("crm.opportunities.write") && permissions.includes("crm.opportunities.read_content");
    current = {org, api, user, permissions, refresh, isCurrent:()=>ticket===generation,
      commercial:{info:{timezone:clock.timezone,can_write:canWrite},stages,assignees}};
    const names = Object.fromEntries(assignees.map(u=>[u.id,u.name]));
    const date = value => value ? new Intl.DateTimeFormat("es-PE",{dateStyle:"medium",timeStyle:"short",timeZone:clock.timezone}).format(new Date(value)) : "Sin fecha";
    return `<div class="view-heading"><div><h3>Tablero comercial</h3><p>Abre una oportunidad para cambiar etapa, responsable o próxima acción. Fechas en ${esc(clock.timezone)}.</p></div><button data-board="refresh" class="secondary-button">Actualizar</button></div>
      <form id="board-filters" class="crm-filters"><label>Responsable<select name="assigned_user_id"><option value="">Todo el equipo</option>${assignees.map(u=>`<option value="${esc(u.id)}" ${u.id===assignee?'selected':''}>${esc(u.name)}</option>`).join("")}</select></label><button class="secondary-button">Aplicar filtros</button></form>
      <div class="commercial-board">${columns.map(({stage,result})=>`<section class="panel board-column" aria-label="${esc(stage.name)}"><h4>${esc(stage.name)} · ${result.total}</h4><p>${{open:"Abierta",won:"Ganada",lost:"Perdida"}[stage.kind]}</p><ul class="commercial-list">${result.items.map(item=>`<li><strong>${esc(item.title)}</strong><p>Responsable: ${esc(names[item.assigned_user_id] || "Integrante del equipo")}</p><p>${item.next_action && new Date(item.next_action.due_at)<new Date(clock.as_of)?'<strong>Acción vencida</strong> · ':''}${esc(item.next_action?.description || item.close_reason || item.no_action_reason || "Sin acción programada")} · ${esc(date(item.next_action?.due_at))}</p><button class="secondary-button" data-board="contact" data-contact="${esc(item.contact_id)}">Abrir ficha del cliente</button>${canWrite?`<button class="secondary-button" data-commercial="edit" data-opportunity="${esc(item.id)}">Editar oportunidad</button>`:""}<button class="secondary-button" data-commercial="history" data-opportunity="${esc(item.id)}">Ver historial</button></li>`).join("") || '<li>Sin oportunidades.</li>'}</ul>
      <nav class="crm-pagination" aria-label="Página de ${esc(stage.name)}"><button data-board="previous" data-stage="${esc(stage.code)}" ${result.page<=1?'disabled':''}>Anterior</button><span>Página ${result.page}</span><button data-board="next" data-stage="${esc(stage.code)}" ${!result.has_next?'disabled':''}>Siguiente</button></nav></section>`).join("")}</div><section class="panel"><div id="commercial-editor"></div><p id="commercial-feedback" role="status"></p></section>`;
  }
  function mount(root) {
    const c=current; if(!c?.isCurrent())return;
    c.root=root; c.controller=new AbortController(); const options={signal:c.controller.signal};
    root.querySelector('#board-filters').addEventListener('submit',event=>{event.preventDefault();assignee=new FormData(event.target).get('assigned_user_id');pages={};c.refresh();},options);
    root.addEventListener('submit',event=>{if(event.target.id==='commercial-form')window.LuriOpportunities.submit(c,event,c.refresh);},options);
    root.addEventListener('click',async event=>{
      if(!c.isCurrent() || c.busy)return;
      const commercial=event.target.closest('[data-commercial]');
      if(commercial)return window.LuriOpportunities.action(c,commercial.dataset.commercial,commercial.dataset.opportunity,c.refresh);
      const button=event.target.closest('[data-board]');if(!button || button.disabled)return;
      const action=button.dataset.board;
      if(action==='refresh')return c.refresh();
      if(action==='previous'||action==='next'){pages[button.dataset.stage]=(pages[button.dataset.stage]||1)+(action==='next'?1:-1);return c.refresh();}
      if(action==='contact'){
        c.busy=true;
        try{await window.LuriCRM.openFromConversation(c.org,c.api,button.dataset.contact,c.refresh);}
        catch(error){if(c.isCurrent())root.querySelector('#commercial-feedback').textContent=error.message;}
        finally{c.busy=false;}
      }
    },options);
  }
  return {render,mount,close,reset};
})();
