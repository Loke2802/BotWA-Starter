/* The CRM stores all records through the authenticated, tenant-scoped API. */
window.LuriCRM = (() => {
  const stages = {lead: "Prospecto", customer: "Cliente", inactive: "Inactivo"};
  const services = {undecided: "Por definir", luri: "Luri", site: "Kalivur Site", marketing: "Marketing", other: "Otro"};
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"})[c]);
  const date = value => value ? new Intl.DateTimeFormat("es-PE", {dateStyle:"medium", timeStyle:"short"}).format(new Date(value)) : "Sin programar";
  let context, generation = 0, dialog;
  let filters = {classification:"", status:"active", due:false, page:1};
  function close() { generation++; if (dialog) {dialog.close(); dialog.remove(); dialog = null;} }
  function reset() { close(); filters = {classification:"", status:"active", due:false, page:1}; }
  function options(values, selected) { return Object.entries(values).map(([key, value]) => `<option value="${esc(key)}" ${key === selected ? "selected" : ""}>${esc(value)}</option>`).join(""); }
  async function render(org, api, refresh) {
    close();
    const ticket = generation;
    const base = `/organizations/${org}/crm`;
    const query = new URLSearchParams({status:filters.status, page:String(filters.page), page_size:"20", due:String(filters.due)});
    if (filters.classification) query.set("classification", filters.classification);
    const [summary, result, assignees] = await Promise.all([api(`${base}/summary`), api(`${base}/customers?${query}`), api(`${base}/assignees`)]);
    if (ticket !== generation) return "";
    context = {org, base, api, refresh, summary, assignees, result};
    const names = Object.fromEntries(assignees.map(x=>[x.id,x.name]));
    return `<div class="view-heading"><div><p class="eyebrow">RELACIONES QUE CRECEN</p><h3>Clientes y oportunidades</h3><p class="muted">Toda la información de tus contactos, en un solo lugar.</p></div>${summary.can_create ? '<button class="primary-button compact-button" data-crm="new">+ Nuevo contacto</button>' : ''}</div>
      <div class="metric-grid crm-metrics">
        <article class="metric-card"><span>Prospectos</span><strong>${summary.leads}</strong><small>Oportunidades por acompañar</small></article>
        <article class="metric-card"><span>Clientes</span><strong>${summary.customers}</strong><small>Relaciones comerciales activas</small></article>
        <article class="metric-card"><span>Inactivos</span><strong>${summary.inactive}</strong><small>Contactos sin actividad comercial</small></article>
        <article class="metric-card follow-up"><span>Seguimientos pendientes</span><strong>${summary.follow_ups_due}</strong><button class="crm-link" data-crm="due">Ver pendientes →</button></article>
      </div>
      <article class="panel"><form id="crm-filters" class="crm-filters">
        <label>Clasificación<select name="classification">${options({"":"Todos",...stages},filters.classification)}</select></label>
        <label>Mostrar<select name="status">${options({active:"Contactos activos",archived:"Archivados"},filters.status)}</select></label>
        <label class="crm-check"><input type="checkbox" name="due" ${filters.due?'checked':''}> Solo seguimientos pendientes</label>
        <button class="secondary-button">Aplicar filtros</button>
      </form><div class="crm-list-heading"><p>${result.total} contactos · Página ${result.page}</p><label>Buscar nombre en esta página<input id="crm-name-filter" type="search" placeholder="Escribe un nombre" maxlength="200"></label></div>
      <div class="crm-cards">${result.items.length ? result.items.map(item=>`<button class="crm-contact" data-crm="open" data-id="${esc(item.id)}" data-name="${esc(item.display_name || 'Sin nombre')}"><span class="crm-avatar" aria-hidden="true">${esc((item.display_name || '?').slice(0,1).toUpperCase())}</span><span class="crm-contact-main"><strong>${esc(item.display_name || 'Sin nombre')}</strong><span>${esc(services[item.service_interest] || item.service_interest)} · ${esc(item.channel_type)}</span><span>Responsable: ${esc(names[item.assigned_user_id] || 'Sin asignar')}</span></span><span class="crm-contact-meta"><span class="status ${esc(item.classification)}">${esc(stages[item.classification])}</span><span>Seguimiento: ${esc(date(item.next_follow_up_at))}</span><span class="crm-link">Abrir ficha →</span></span></button>`).join('') : '<div class="crm-empty"><h4>No hay contactos con estos filtros</h4><p>Prueba otra clasificación o registra tu primer contacto.</p></div>'}</div>
      <p id="crm-no-match" class="empty" hidden>No hay coincidencias en esta página.</p>
      <div class="crm-pagination"><button class="secondary-button" data-crm="previous" ${result.page<=1?'disabled':''}>← Anterior</button><span>${result.total ? (result.page-1)*20+1 : 0}–${Math.min(result.page*20,result.total)} de ${result.total}</span><button class="secondary-button" data-crm="next" ${!result.has_next?'disabled':''}>Siguiente →</button></div></article>`;
  }
  function mount(root) {
    root.querySelector('#crm-filters')?.addEventListener('submit', event=>{
      event.preventDefault(); const f = new FormData(event.currentTarget);
      filters={classification:f.get('classification'),status:f.get('status'),due:f.has('due'),page:1};context.refresh();
    });
    root.querySelector('#crm-name-filter')?.addEventListener('input', event=>{
      let matches=0; const term=event.target.value.toLocaleLowerCase('es').trim();
      root.querySelectorAll('.crm-contact').forEach(card=>{card.hidden=!card.dataset.name.toLocaleLowerCase('es').includes(term);if(!card.hidden)matches++;});
      root.querySelector('#crm-no-match').hidden=matches>0 || !context.result.items.length;
    });
    root.querySelectorAll('[data-crm]').forEach(button=>button.addEventListener('click',async()=>{
      const action=button.dataset.crm;
      if(action==='previous'||action==='next'){filters.page+=action==='next'?1:-1;return context.refresh();}
      if(action==='due'){filters={classification:'',status:'active',due:true,page:1};return context.refresh();}
      button.disabled=true;
      try { await open(button.dataset.id || null); }
      catch(error){ const notice=document.querySelector('#portal-notice');notice.textContent=error.message;notice.hidden=false; }
      finally {button.disabled=false;}
    }));
  }
  async function open(id) {
    const current = context, ticket=generation;
    const item=id?await current.api(`${current.base}/customers/${id}`):null;
    if(ticket!==generation) return;
    const editable=item?item.can_edit:true;
    const sensitive=item?item.can_read_sensitive:true;
    dialog=document.createElement('dialog');dialog.className='crm-dialog';dialog.setAttribute('aria-labelledby','crm-title');
    const localDate=item?.next_follow_up_at ? new Date(new Date(item.next_follow_up_at).getTime()-new Date(item.next_follow_up_at).getTimezoneOffset()*60000).toISOString().slice(0,16) : '';
    dialog.innerHTML=`<div class="modal-heading"><div><p class="eyebrow">${id?'FICHA DEL CONTACTO':'CRECE TU CARTERA'}</p><h3 id="crm-title">${id?esc(item.display_name || 'Contacto'):'Nuevo contacto'}</h3></div><button type="button" class="icon-button" id="crm-close" aria-label="Cerrar ficha">×</button></div>
      <p class="muted">${id?'Consulta y organiza la relación con este contacto.':'Empieza con su nombre y WhatsApp. Podrás completar la ficha después.'}</p>
      <form id="crm-edit"><fieldset ${!editable?'disabled':''}><div class="form-grid">
        <label>Nombre<input name="display_name" value="${esc(item?.display_name)}" minlength="2" maxlength="200" required></label>
        <label>WhatsApp ${id?'':'con código de país'}<input name="whatsapp" type="tel" value="${esc(item?.external_identifier ? '+'+item.external_identifier : '')}" ${id?'disabled': 'required pattern="\\+[1-9][0-9]{7,14}"'} placeholder="${id&&!sensitive?'Restringido por tu rol':'+51955491097'}"></label>
        <label>Clasificación<select name="classification">${options(stages,item?.classification || 'lead')}</select></label>
        <label>Servicio de interés<select name="service_interest">${options(services,item?.service_interest || 'undecided')}</select></label>
        <label>Responsable<select name="assigned_user_id"><option value="">Sin asignar</option>${current.assignees.map(u=>`<option value="${esc(u.id)}" ${u.id===item?.assigned_user_id?'selected':''}>${esc(u.name)}</option>`).join('')}</select></label>
        <label>Próximo seguimiento<input name="next_follow_up_at" type="datetime-local" value="${localDate}"><small>Hora local de tu dispositivo. Vacío = sin programar.</small></label>
        ${sensitive?`<label class="full-width">Notas de atención<textarea name="notes" rows="5" maxlength="4000" placeholder="Contexto, acuerdos y siguiente paso">${esc(item?.notes || '')}</textarea></label>`:'<p class="muted full-width">Tu rol no permite ver ni editar teléfono y notas.</p>'}
      </div></fieldset><p id="crm-error" class="form-error" role="alert"></p><p id="crm-saved" role="status"></p>
      <div class="modal-actions">${id&&current.summary.can_archive?`<button type="button" class="secondary-button" id="crm-archive">${item.status==='archived'?'Reactivar contacto':'Archivar contacto'}</button>`:''}<button type="button" class="secondary-button" id="crm-cancel">Cerrar</button>${editable?'<button class="primary-button compact-button" type="submit">Guardar contacto</button>':''}</div></form>`;
    document.body.append(dialog);const modal=dialog;modal.showModal();
    const dismiss=()=>{if(dialog===modal)close();};
    modal.querySelector('#crm-close').onclick=dismiss;modal.querySelector('#crm-cancel').onclick=dismiss;
    let busy=false;
    modal.addEventListener('cancel',event=>{if(busy)event.preventDefault();else dismiss();});
    const setBusy=value=>{busy=value;modal.querySelectorAll('button').forEach(b=>b.disabled=value);};
    modal.querySelector('#crm-edit').onsubmit=async event=>{
      event.preventDefault();if(busy||!editable)return;
      const f=new FormData(event.currentTarget);
      const payload={display_name:f.get('display_name'),classification:f.get('classification'),service_interest:f.get('service_interest'),assigned_user_id:f.get('assigned_user_id')||null,next_follow_up_at:f.get('next_follow_up_at')?new Date(f.get('next_follow_up_at')).toISOString():null};
      if(sensitive)payload.notes=f.get('notes');
      if(id)payload.version=item.version;else payload.whatsapp=f.get('whatsapp');
      modal.querySelector('#crm-error').textContent='';setBusy(true);
      try {await current.api(`${current.base}/customers${id?'/'+id:''}`,{method:id?'PUT':'POST',body:JSON.stringify(payload)});
        dismiss();await current.refresh();const notice=document.querySelector('#portal-notice');notice.textContent='Contacto guardado correctamente.';notice.hidden=false;
      }catch(error){modal.querySelector('#crm-error').textContent=error.message;}
      finally{setBusy(false);}
    };
    modal.querySelector('#crm-archive')?.addEventListener('click',async()=>{
      const action=item.status==='archived'?'reactivate':'archive';
      if(!window.confirm(action==='archive'?'¿Archivar este contacto? Se conservarán sus datos y podrás reactivarlo.':'¿Reactivar este contacto?'))return;
      setBusy(true);
      try {await current.api(`/organizations/${current.org}/contacts/${id}/${action}`,{method:'POST'});dismiss();await current.refresh();}
      catch(error){modal.querySelector('#crm-error').textContent=error.message;}
      finally{setBusy(false);}
    });
  }
  return {render,mount,close,reset};
})();
