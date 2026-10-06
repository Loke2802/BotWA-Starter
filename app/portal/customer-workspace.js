/* Customer workspace reuses opportunity commands; no independent sales state. */
window.LuriCustomerWorkspace = (() => {
 const esc=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[c]);
 async function attach(modal,context,contact,isCurrent){
  const section=document.createElement('section');section.className='panel';modal.append(section);
  let pages={opportunities:1,conversations:1,activities:1,actions:1},generation=0,c;
  const live=()=>modal.isConnected&&isCurrent();
  async function refresh(){
   const ticket=++generation;const base=`/organizations/${context.org}/crm/customers/${contact}`;
   try{
    const [workspace,activities,me,actions]=await Promise.all([context.api(`${base}/workspace?page=${pages.opportunities}&conversation_page=${pages.conversations}`),context.api(`${base}/activities?page=${pages.activities}`),context.api('/auth/me'),context.api(`${base}/action-history?page=${pages.actions}`)]);
    if(!live()||ticket!==generation)return;
    const archive=modal.querySelector('#crm-archive');if(archive&&workspace.contact_id!==contact)archive.hidden=true;
    const names=Object.fromEntries(context.assignees.map(u=>[u.id,u.name]));
    const date=value=>new Intl.DateTimeFormat('es-PE',{dateStyle:'medium',timeStyle:'short',timeZone:workspace.timezone}).format(new Date(value));
    c={org:context.org,api:context.api,user:me.user,selected:null,root:section,isCurrent:()=>live()&&ticket===generation,commercial:{info:{contact_id:workspace.contact_id,timezone:workspace.timezone,can_write:workspace.can_write},stages:workspace.stages,assignees:context.assignees},workspace};
    const nav=(name,result)=>`<nav class="crm-pagination" aria-label="${name}"><button type="button" data-customer="previous" data-list="${name}" ${pages[name]<=1?'disabled':''}>Anterior</button><span>Página ${pages[name]} · ${result.total}</span><button type="button" data-customer="next" data-list="${name}" ${!result.has_next?'disabled':''}>Siguiente</button></nav>`;
    section.innerHTML=`<h4>Ficha comercial</h4>${workspace.contact_id!==contact?`<p>Este contacto fue unido. <button type="button" data-customer="principal" data-id="${esc(workspace.contact_id)}">Abrir ficha principal</button></p>`:""}<p>Fechas en ${esc(workspace.timezone)}.</p>${workspace.can_write?'<button type="button" data-commercial="new" class="primary-button">Crear oportunidad para este cliente</button>':''}
      ${workspace.merged_origins?.length?`<h4>Fichas originales conservadas</h4><ul>${workspace.merged_origins.map(o=>`<li>${esc(o.name)} <button type="button" data-customer="principal" data-id="${esc(o.id)}">Ver ficha original</button></li>`).join("")}</ul>`:""}<h4>Oportunidades y próximas acciones</h4><ul class="commercial-list">${workspace.opportunities.items.map(o=>`<li><strong>${esc(o.title)}</strong> · ${esc(workspace.stages.find(s=>s.code===o.stage_code)?.name||o.stage_code)}<p>Responsable: ${esc(names[o.assigned_user_id]||'Integrante del equipo')}</p><p>${esc(o.next_action?.description||o.close_reason||o.no_action_reason||'Sin acción')} ${o.next_action?' · '+esc(date(o.next_action.due_at)):''}</p>${workspace.can_write?`<button type="button" class="secondary-button" data-commercial="edit" data-opportunity="${esc(o.id)}">Editar y programar próxima acción</button>`:''}<button type="button" class="secondary-button" data-commercial="history" data-opportunity="${esc(o.id)}">Ver historial</button></li>`).join('')||'<li>Sin oportunidades.</li>'}</ul>${nav('opportunities',workspace.opportunities)}
      <div id="commercial-editor"></div><p id="commercial-feedback" role="status"></p>
      <h4>Conversaciones</h4>${workspace.can_read_conversations?`<ul>${workspace.conversations.map(v=>`<li>${esc(v.status)} · ${esc(date(v.created_at))}<button type="button" class="secondary-button" data-customer="conversation" data-id="${esc(v.id)}">Abrir conversación</button></li>`).join('')||'<li>Sin conversaciones.</li>'}</ul>${nav('conversations',{total:workspace.conversation_total,has_next:workspace.conversations_has_next})}`:'<p>Sin permiso para consultar conversaciones.</p>'}
      ${workspace.can_write&&workspace.conversations.length?`<label>Conversación para sugerencia IA<select id="customer-ai-conversation">${workspace.conversations.map(v=>`<option value="${esc(v.id)}">${esc(date(v.created_at))} · ${esc(v.status)}</option>`).join('')}</select></label><label>Aplicar sugerencia a<select id="customer-ai-target"><option value="">Nueva oportunidad</option>${workspace.opportunities.items.filter(o=>o.stage_kind==="open").map(o=>`<option value="${esc(o.id)}">${esc(o.title)}</option>`).join("")}</select></label><button type="button" class="secondary-button" data-customer="suggest">Consultar sugerencia de IA</button><div id="customer-suggestion"></div>`:''}
      <h4>Historial de acciones</h4><ul>${actions.items.map(a=>`<li><strong>${{pending:"Pendiente",completed:"Completada",cancelled:"Sustituida o cancelada"}[a.status]}</strong> · ${esc(a.description)}<p>Programada: ${esc(date(a.due_at))}${a.resolved_at?" · Finalizada: "+esc(date(a.resolved_at)):""} · ${esc(names[a.assigned_user_id]||"Integrante del equipo")}</p></li>`).join("")||"<li>Sin acciones.</li>"}</ul>${nav("actions",actions)}
      <h4>Actividades registradas</h4><ul>${activities.items.map(a=>`<li>${{call:'Llamada',meeting:'Reunión',note:'Nota'}[a.kind]} · ${esc(date(a.occurred_at))} · ${esc(names[a.actor_user_id]||'Integrante del equipo')}<p>${esc(a.description)}</p>${a.opportunity_id?'<small>Vinculada a una oportunidad</small>':''}</li>`).join('')||'<li>Sin actividades.</li>'}</ul>${nav('activities',activities)}
      ${workspace.can_write?`<form id="customer-activity"><h4>Registrar actividad realizada</h4><label>Tipo<select name="kind"><option value="call">Llamada</option><option value="meeting">Reunión</option><option value="note">Nota</option></select></label><label>Descripción de actividad<textarea name="description" required maxlength="4000"></textarea></label><label>Fecha de actividad<input type="datetime-local" name="occurred_at" required></label><label>Oportunidad relacionada<select name="opportunity_id"><option value="">Solo cliente</option>${workspace.opportunities.items.map(o=>`<option value="${esc(o.id)}">${esc(o.title)}</option>`).join('')}</select></label><small>Para una acción futura, edita la oportunidad; esta lista registra actividades realizadas.</small><button class="primary-button" type="submit">Guardar actividad</button></form>`:''}<p id="customer-feedback" role="status"></p>`;
   }catch(error){if(live()&&ticket===generation)section.textContent=`No se pudo cargar la ficha comercial: ${error.message}`;}
  }
  section.addEventListener('click',async event=>{
   if(!c?.isCurrent()||c.busy)return;
   const commercial=event.target.closest('[data-commercial]');if(commercial)return window.LuriOpportunities.action(c,commercial.dataset.commercial,commercial.dataset.opportunity,refresh);
   const button=event.target.closest('[data-customer]');if(!button||button.disabled)return;
   const action=button.dataset.customer;
   if(action==='previous'||action==='next'){pages[button.dataset.list]+=action==='next'?1:-1;return refresh();}
   if(action==='conversation'){modal.dispatchEvent(new CustomEvent('luri-open-conversation',{bubbles:true,detail:{org:c.org,id:button.dataset.id}}));return;}
   if(action==='principal'){return window.LuriCRM.openFromConversation(c.org,c.api,button.dataset.id,context.refresh);}
   if(action==='accept' && c.suggestion.opportunity_id){
    const actor=c;actor.busy=true;
    try{const item=await actor.api(`/organizations/${actor.org}/crm/opportunities/${actor.suggestion.opportunity_id}`);if(!actor.isCurrent())return;
     if(item.version!==actor.suggestion.expected_version){section.querySelector('#customer-feedback').textContent='La oportunidad cambió. Consulta de nuevo la sugerencia antes de aplicarla.';return;}
     const proposed={...item,need:actor.suggestion.need,stage_code:actor.suggestion.stage_code,no_action_reason:null,next_action:{description:actor.suggestion.next_action,due_at:item.next_action?.due_at}};
     window.LuriOpportunities.form(actor,proposed);section.querySelector('#customer-feedback').textContent='Cambios propuestos en el editor. Se conservan importe y responsable; revisa etapa, acción y fecha antes de guardar.';
    }catch(error){if(actor.isCurrent())section.querySelector('#customer-feedback').textContent=error.message;}finally{actor.busy=false;}return;
   }
   if(action==='accept'){
    c.commercialDraft={title:'Seguimiento comercial',need:c.suggestion.need,stage_code:c.suggestion.stage_code,next_action:{description:c.suggestion.next_action}};
    window.LuriOpportunities.form(c);section.querySelector('#customer-feedback').textContent='Borrador aplicado. Revisa los datos y elige responsable y fecha antes de guardar.';return;
   }
   if(action==='suggest'){
    c.busy=true;const chosen=section.querySelector('#customer-ai-conversation').value,target=section.querySelector('#customer-ai-target').value;
    try{
     const suggestion=await c.api(target?`/organizations/${c.org}/crm/opportunities/${target}/suggestions/${chosen}`:`/organizations/${c.org}/crm/customers/${contact}/suggestions/${chosen}`);if(!c.isCurrent())return;c.suggestion=suggestion;
     section.querySelector('#customer-suggestion').innerHTML=`<p>${esc(suggestion.explanation)}</p>${suggestion.available?`${suggestion.opportunity_id?`<p>Revisión de oportunidad · versión ${suggestion.expected_version}</p><p>Necesidad actual: ${esc(suggestion.current_need||"Sin necesidad")}</p><p>Etapa actual: ${esc(suggestion.current_stage_code)}</p><p>Acción actual: ${esc(suggestion.current_action||"Sin acción")}</p>`:""}<p>Necesidad propuesta: ${esc(suggestion.need)}</p><p>Etapa sugerida: ${esc(c.commercial.stages.find(s=>s.code===suggestion.stage_code)?.name||suggestion.stage_code)}</p><p>Acción sugerida: ${esc(suggestion.next_action)}</p><ul>${suggestion.evidence.map(quote=>`<li>${esc(quote)}</li>`).join('')}</ul><button type="button" class="secondary-button" data-customer="accept">Usar como borrador</button>`:''}`;
    }catch(error){if(c.isCurrent())section.querySelector('#customer-feedback').textContent=error.message;}
    finally{c.busy=false;}
   }
  });
  section.addEventListener('submit',async event=>{
   if(event.target.id==='commercial-form')return window.LuriOpportunities.submit(c,event,refresh);
   if(event.target.id!=='customer-activity')return;event.preventDefault();if(!c?.isCurrent()||c.busy)return;
   const f=new FormData(event.target),payload={kind:f.get('kind'),description:f.get('description'),occurred_at:new Date(f.get('occurred_at')).toISOString(),opportunity_id:f.get('opportunity_id')||null};
   const actor=c;c.busy=true;const form=event.target;form.querySelector('button').disabled=true;
   try{
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)))),b=>b.toString(16).padStart(2,'0')).join('');
    const storage=`luri.activity.${actor.user.id}.${actor.org}.${contact}`,old=JSON.parse(sessionStorage.getItem(storage)||'null'),key=old?.hash===hash?old.key:crypto.randomUUID();sessionStorage.setItem(storage,JSON.stringify({hash,key}));
    if(!actor.isCurrent())return;
    await actor.api(`/organizations/${actor.org}/crm/customers/${contact}/activities`,{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify(payload)});
    sessionStorage.removeItem(storage);if(actor.isCurrent()){await refresh();if(c.isCurrent())section.querySelector('#customer-feedback').textContent='Actividad guardada correctamente.';}
   }catch(error){if(actor.isCurrent())section.querySelector('#customer-feedback').textContent=error.message+' Reintentar conserva la clave para evitar duplicados.';}
   finally{actor.busy=false;if(actor.isCurrent())form.querySelector('button').disabled=false;}
  });
  await refresh();
 }
 return {attach};
})();
