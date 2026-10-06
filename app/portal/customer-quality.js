/* Reviewed customer consolidation. No automatic merges or private data storage. */
window.LuriCustomerQuality=(()=>{
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
 let current,generation=0,page=1;
 function close(){generation++;current?.controller?.abort();current=null;}
 function reset(){close();page=1;}
 async function render(org,api,user,permissions,refresh){
  const ticket=++generation;
  if(!['contacts.read','contacts.read_sensitive','contacts.update','contacts.archive','crm.opportunities.read','crm.opportunities.write','crm.opportunities.read_content'].every(p=>permissions.includes(p)))return '<p>No tienes permiso para revisar y unir clientes.</p>';
  const result=await api(`/organizations/${org}/crm/duplicates?page=${page}`);if(ticket!==generation)return '';
  current={org,api,refresh,isCurrent:()=>ticket===generation,items:result.items};
  return `<div class="view-heading"><div><h3>Calidad de clientes</h3><p>Coincidencias posibles. Revisa identidades y elige la ficha principal antes de unir.</p></div><button data-quality="refresh" class="secondary-button">Actualizar</button></div><section class="panel"><p>${result.scanned} contactos examinados.${result.scan_limited?' La búsqueda automática se limita a los primeros 2000 contactos activos.':''} Un nombre coincidente no confirma que sea la misma persona.</p><ul>${result.items.map((r,i)=>`<li><strong>${esc(r.source_name)}</strong> y <strong>${esc(r.target_name)}</strong> · coincidencia: ${r.reasons.map(esc).join(', ')}<button data-quality="review" data-index="${i}" class="secondary-button">Revisar unión</button><button data-quality="reverse" data-index="${i}" class="secondary-button">Revisar con el otro principal</button></li>`).join('')||'<li>Sin posibles duplicados en la búsqueda.</li>'}</ul><nav class="crm-pagination"><button data-quality="previous" ${page<=1?'disabled':''}>Anterior</button><span>Página ${page}</span><button data-quality="next" ${!result.has_next?'disabled':''}>Siguiente</button></nav><div id="merge-review"></div><p id="quality-feedback" role="status"></p></section>`;
 }
 function mount(root){const c=current;if(!c?.isCurrent())return;c.controller=new AbortController();root.addEventListener('click',async event=>{
  const button=event.target.closest('[data-quality]');if(!button||c.busy||!c.isCurrent())return;
  const action=button.dataset.quality;if(action==='refresh')return c.refresh();if(action==='previous'||action==='next'){page+=action==='next'?1:-1;return c.refresh();}
  c.busy=true;let saved=false;
  try{
   if(action==='review'||action==='reverse'){
    const pair=c.items[Number(button.dataset.index)];const source=action==='reverse'?pair.target_id:pair.source_id,target=action==='reverse'?pair.source_id:pair.target_id;
    const review=await c.api(`/organizations/${c.org}/crm/merge-preview?source_id=${source}&target_id=${target}`);if(!c.isCurrent())return;c.review=review;
    const card=(r,label)=>`<article><h4>${label}: ${esc(r.name)}</h4><p>${esc(r.channel)} · ${esc(r.identifier)}</p><p>Notas: ${esc(r.notes||'Sin notas')}</p><p>${r.opportunities} oportunidades · ${r.conversations} conversaciones · ${r.activities} actividades</p><p>Clasificación: ${esc(r.profile.classification||'Sin ficha')} · Interés: ${esc(r.profile.service_interest||'Sin definir')} · Responsable: ${esc(r.profile.assigned_user_id||'Sin asignar')} · Seguimiento: ${esc(r.profile.next_follow_up_at||'Sin fecha')}</p></article>`;
    root.querySelector('#merge-review').innerHTML=`<h4>Revisión de unión</h4>${card(review.target,'Principal que se conservará')}${card(review.source,'Origen que se archivará')}<p>${esc(review.explanation)}</p><label><input type="checkbox" id="merge-confirm"> He revisado las identidades y confirmo que pertenecen al mismo cliente.</label><button data-quality="merge" class="primary-button">Confirmar unión revisada</button>`;
   }
   if(action==='merge'){
    if(!root.querySelector('#merge-confirm')?.checked){root.querySelector('#quality-feedback').textContent='Confirma la revisión de las identidades antes de unir.';return;}
    const r=c.review;await c.api(`/organizations/${c.org}/crm/customer-merges`,{method:'POST',body:JSON.stringify({source_id:r.source.id,target_id:r.target.id,review_token:r.token})});saved=true;
    if(c.isCurrent()){await c.refresh();if(current?.org!==c.org)return;const feedback=root.querySelector('#quality-feedback');if(feedback)feedback.textContent='Clientes unidos. La ficha principal reúne los registros; el origen y su historial se conservan.';}
   }
  }catch(error){if(c.isCurrent())root.querySelector('#quality-feedback').textContent=saved?'Unión guardada. Pulsa Actualizar para renovar la lista.':`${error.message} Si los datos cambiaron, revisa de nuevo; un reintento de la misma unión no duplica registros.`;}
  finally{c.busy=false;}
 },{signal:c.controller.signal});}
 return {render,mount,close,reset};
})();
