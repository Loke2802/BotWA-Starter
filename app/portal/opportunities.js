/* Commercial UI. The backend owns tenant, contact, stage and action authority. */
window.LuriOpportunities = (() => {
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  const date = (value, zone) => value ? new Intl.DateTimeFormat("es-PE", {dateStyle:"medium", timeStyle:"short", timeZone:zone}).format(new Date(value)) : "Sin programar";
  const local = value => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset()*60000).toISOString().slice(0,16) : "";
  const button = (name, text, id="") => `<button type="button" class="secondary-button" data-commercial="${name}" data-opportunity="${esc(id)}">${esc(text)}</button>`;
  const alive = c => c.root?.isConnected && c.isCurrent();

  async function load(c) {
    if (!c.permissions.includes("crm.opportunities.read") || !c.permissions.includes("contacts.read")) return null;
    const base = `/organizations/${c.org}`;
    const info = await c.api(`${base}/conversations/${c.selected}/commercial-context`);
    if (!info.contact_id) return {info};
    const [customer, items, linked, stages, assignees] = await Promise.all([
      c.api(`${base}/crm/customers/${info.contact_id}`),
      c.api(`${base}/crm/opportunities?contact_id=${info.contact_id}&page=${c.commercialPage || 1}&page_size=20`),
      c.api(`${base}/crm/opportunities?conversation_id=${c.selected}&page_size=100`),
      c.api(`${base}/crm/stages`), c.api(`${base}/crm/assignees`),
    ]);
    return {info, customer, items, linked, stages, assignees};
  }
  function markup(c) {
    const data = c.commercial;
    if (!data) return "";
    const {info, customer, items, linked, stages, assignees} = data;
    const account = `${info.channel_type} · ${info.account_name || "Cuenta sin nombre"} · ${info.channel_configuration_id || "Sin cuenta vinculada"}`;
    if (!customer) return `<section class="panel"><h4>Ficha comercial</h4><p>${esc(account)}</p><p>Esta conversación todavía no tiene un contacto vinculado. Requiere revisar el registro de identidad antes de crear una oportunidad.</p></section>`;
    const linkedIds = new Set(linked.items.map(x=>x.id));
    const names = Object.fromEntries(assignees.map(x=>[x.id,x.name]));
    const stageNames = Object.fromEntries(stages.map(x=>[x.code,x.name]));
    return `<section class="panel"><h4>Ficha y oportunidades</h4><p>${esc(account)}</p><p>${esc(customer.display_name || "Contacto")} · ${esc(customer.classification)}</p>
      <div class="conversation-actions">${button("contact", "Abrir ficha del cliente")}${info.can_write ? button("new", "Crear oportunidad") : ""}</div>
      <p>Fechas de seguimiento en ${esc(info.timezone)}. La atención y las etapas comerciales son independientes.</p>
      <ul class="commercial-list">${items.items.map(item=>`<li><strong>${esc(item.title)}</strong> · ${esc(stageNames[item.stage_code] || item.stage_code)}${linkedIds.has(item.id) ? " · Vinculada a esta conversación" : ""}
        <p>Responsable: ${esc(names[item.assigned_user_id] || "Integrante del equipo")}</p><p>Próxima acción: ${esc(item.next_action?.description || item.no_action_reason || "Sin acción")} · ${esc(date(item.next_action?.due_at, info.timezone))}</p>
        ${info.can_write ? button("edit", "Editar oportunidad", item.id) + (linkedIds.has(item.id) ? "" : button("link", "Vincular a esta conversación", item.id)) : ""}${button("history", "Ver historial", item.id)}</li>`).join("") || "<li>Sin oportunidades para este contacto.</li>"}</ul>
      <nav class="crm-pagination" aria-label="Oportunidades del contacto"><button type="button" data-commercial="previous" ${items.page<=1 ? "disabled" : ""}>Anterior</button><span>Página ${items.page} · ${items.total} oportunidades</span><button type="button" data-commercial="next" ${!items.has_next ? "disabled" : ""}>Siguiente</button></nav>
      <div id="commercial-editor"></div><p id="commercial-feedback" role="status"></p></section>`;
  }
  function form(c, item=null) {
    const data = c.commercial;
    c.commercialEdit = item;
    const closed = item && item.stage_kind !== "open";
    const draft = item ? null : c.commercialDraft;
    c.root.querySelector("#commercial-editor").innerHTML = `<form id="commercial-form"><h4>${item ? "Editar oportunidad" : "Nueva oportunidad"}</h4><div class="form-grid">
      <label>Título<input name="title" value="${esc(item?.title || draft?.title)}" required maxlength="200"></label>
      <label>Etapa<select name="stage_code">${data.stages.filter(s=>item || s.kind==="open").map(s=>`<option value="${esc(s.code)}" ${s.code===(item?.stage_code || draft?.stage_code) ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
      <label>Responsable<select name="assigned_user_id" required><option value="">Seleccionar responsable</option>${data.assignees.map(u=>`<option value="${esc(u.id)}" ${u.id===(item?.assigned_user_id || draft?.assigned_user_id) ? "selected" : ""}>${esc(u.name)}</option>`).join("")}</select></label>
      <label>Necesidad<textarea name="need" maxlength="4000">${esc(item?.need || draft?.need)}</textarea></label>
      <label><input type="checkbox" name="defer_action" ${item?.no_action_reason || draft?.no_action_reason ? "checked" : ""}> Sin acción programada por ahora</label>
      <label>Motivo sin acción<input name="no_action_reason" maxlength="1000" value="${esc(item?.no_action_reason || draft?.no_action_reason)}"></label>
      <label>Próxima acción<input name="description" maxlength="2000" value="${esc(item?.next_action?.description || draft?.next_action?.description)}" ${closed ? "" : "required"}></label>
      <label>Fecha y hora<input type="datetime-local" name="due_at" value="${local(item?.next_action?.due_at || draft?.next_action?.due_at)}" ${closed ? "" : "required"}><small>Entrada en hora de tu dispositivo (${esc(Intl.DateTimeFormat().resolvedOptions().timeZone)}); se mostrará en ${esc(data.info.timezone)}.</small></label>
      <label>Motivo de cierre<input name="close_reason" maxlength="1000" value="${esc(item?.close_reason)}"></label>
      ${item?.next_action ? '<label><input type="checkbox" name="complete_previous_action"> Marcar la acción anterior como completada; en otro caso se conserva como sustituida.</label>' : ""}
      </div><p class="form-error" id="commercial-form-error" role="alert"></p><button class="primary-button" type="submit">Guardar oportunidad</button>${button("cancel", "Cancelar")}</form>`;
    const f = c.root.querySelector("#commercial-form");
    const requirements = () => {
      const kind = data.stages.find(s=>s.code===f.elements.stage_code.value).kind;
      const terminal = kind!=="open";
      const deferred = !terminal && f.elements.defer_action.checked;
      f.elements.description.required = !terminal && !deferred; f.elements.due_at.required = !terminal && !deferred;
      f.elements.description.disabled = terminal || deferred; f.elements.due_at.disabled = terminal || deferred;
      f.elements.defer_action.disabled = terminal;
      f.elements.no_action_reason.required = deferred; f.elements.no_action_reason.disabled = !deferred;
      f.elements.close_reason.required = terminal; f.elements.close_reason.disabled = !terminal;
    };
    f.elements.stage_code.addEventListener("change", requirements); requirements();
    f.elements.defer_action.addEventListener("change", requirements);
  }
  async function action(c, name, id, refresh) {
    if (!alive(c) || c.busy) return;
    const base = `/organizations/${c.org}`;
    if (name === "cancel") {c.root.querySelector("#commercial-editor").innerHTML=""; return;}
    c.busy = true;
    try {
      if (name === "contact") await window.LuriCRM.openFromConversation(c.org, c.api, c.commercial.info.contact_id, refresh);
      if (name === "new") form(c);
      if (name === "edit") {const item=await c.api(`${base}/crm/opportunities/${id}`); if(alive(c))form(c,item);}
      if (name === "link") {await c.api(`${base}/crm/opportunities/${id}/conversations/${c.selected}`, {method:"PUT"}); if(alive(c))await refresh();}
      if (name === "previous" || name === "next") {c.commercialPage=(c.commercialPage || 1)+(name==="next"?1:-1); await refresh();}
      if (name === "history") {
        const rows=await c.api(`${base}/crm/opportunities/${id}/history?page_size=20`);
        if(alive(c)) c.root.querySelector("#commercial-editor").innerHTML=`<h4>Historial comercial (últimas 20 versiones)</h4><ol>${rows.map(h=>`<li>Versión ${h.version} · ${esc(date(h.occurred_at,c.commercial.info.timezone))} · ${esc(h.snapshot.title)} · ${esc(c.commercial.stages.find(s=>s.code===h.snapshot.stage_code)?.name || h.snapshot.stage_code)} · Responsable ${esc(c.commercial.assignees.find(u=>u.id===h.snapshot.assigned_user_id)?.name || "Integrante del equipo")} · Modificado por ${esc(c.commercial.assignees.find(u=>u.id===h.actor_user_id)?.name || "Integrante del equipo")}<p>${esc(h.snapshot.next_action?.description || h.snapshot.close_reason || h.snapshot.no_action_reason)}</p></li>`).join("")}</ol>`;
      }
    } catch(error) {if(alive(c)) c.root.querySelector("#commercial-feedback").textContent=error.message;}
    finally {c.busy=false;}
  }
  async function submit(c, event, refresh) {
    event.preventDefault(); if(!alive(c)||c.busy)return;
    const f=new FormData(event.target), item=c.commercialEdit;
    const stage=c.commercial.stages.find(s=>s.code===f.get("stage_code"));
    const payload={title:f.get("title"), need:f.get("need")||null, stage_code:stage.code, assigned_user_id:f.get("assigned_user_id"),
      next_action:stage.kind==="open" && !f.has("defer_action") ? {description:f.get("description"),due_at:new Date(f.get("due_at")).toISOString()} : null,
      no_action_reason:stage.kind==="open" && f.has("defer_action") ? f.get("no_action_reason") : null,
      close_reason:stage.kind==="open" ? null : f.get("close_reason"), amount:item?.amount ?? null, currency:item?.currency ?? null};
    if(item){payload.version=item.version;payload.complete_previous_action=f.has("complete_previous_action");}
    else {payload.contact_id=c.commercial.info.contact_id;payload.conversation_id=c.selected;c.commercialDraft=payload;}
    c.busy=true; const formNode=event.target; formNode.querySelectorAll("button").forEach(b=>b.disabled=true);
    c.root.querySelector("#commercial-feedback").textContent="Guardando oportunidad…";
    c.root.querySelector("#commercial-form-error").textContent="";
    let saved=false;
    try {
      let key=null;
      if(!item){
        const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(JSON.stringify(payload)))),b=>b.toString(16).padStart(2,"0")).join("");
        const storage=`luri.opportunity.${c.user.id}.${c.org}.${c.selected}`;
        const old=JSON.parse(sessionStorage.getItem(storage)||"null"); key=old?.hash===hash?old.key:crypto.randomUUID();
        sessionStorage.setItem(storage,JSON.stringify({hash,key}));
      }
      if(!alive(c))return;
      await c.api(`/organizations/${c.org}/crm/opportunities${item?'/'+item.id:''}`, {method:item?"PATCH":"POST",headers:key?{"Idempotency-Key":key}:{},body:JSON.stringify(payload)});
      saved=true;c.commercialDraft=null;
      if(!item)sessionStorage.removeItem(`luri.opportunity.${c.user.id}.${c.org}.${c.selected}`);
      if(alive(c)){await refresh();c.root.querySelector("#commercial-feedback").textContent="Oportunidad guardada correctamente.";}
    } catch(error){if(alive(c) && !saved)c.root.querySelector("#commercial-feedback").textContent="";if(alive(c)) (c.root.querySelector("#commercial-form-error")||c.root.querySelector("#commercial-feedback")).textContent=saved?"Guardada, pero no se pudo actualizar la vista. Pulsa Actualizar.":item && error.status===409 ? "Esta oportunidad cambió en otra sesión. Pulsa Actualizar y revisa el historial antes de volver a editar." : item ? error.message : `${error.message} Reintentar la misma creación conserva la clave y evita duplicados.`;}
    finally{c.busy=false;if(alive(c))formNode.querySelectorAll("button").forEach(b=>b.disabled=false);}
  }
  return {load,markup,action,submit};
})();
