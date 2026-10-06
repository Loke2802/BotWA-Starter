/* Configuration changes names/order/additions; existing codes and kinds stay stable. */
window.LuriStages = (() => {
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"})[c]);
  let generation=0,current;
  function close(){generation++;current?.controller?.abort();current=null;}
  function reset(){close();}
  async function render(org,api,user,permissions,refresh){
    const ticket=++generation;
    if(!['crm.stages.manage','crm.opportunities.read','contacts.read'].every(p=>permissions.includes(p)))return '<p class="empty">No tienes permiso para configurar las etapas comerciales.</p>';
    const stages=await api(`/organizations/${org}/crm/stages`);if(ticket!==generation)return "";
    current={org,api,refresh,original:stages,draft:stages.map(s=>({...s})),isCurrent:()=>ticket===generation};
    current.existing=new Set(current.draft);
    return `<div class="view-heading"><div><h3>Etapas comerciales</h3><p>Personaliza nombres y orden. Las oportunidades conservan su etapa y su historial.</p></div><button data-stages="refresh" class="secondary-button">Actualizar</button></div><section class="panel"><form id="stages-form"><div id="stages-rows"></div><button type="button" data-stages="add" class="secondary-button">Añadir etapa abierta</button><p id="stages-feedback" role="alert"></p><button type="submit" class="primary-button">Guardar etapas</button></form></section>`;
  }
  function rows(c){
    c.root.querySelector('#stages-rows').innerHTML=c.draft.map((s,i)=>`<fieldset class="stage-row"><legend>Etapa ${i+1} · ${{open:'Abierta',won:'Ganada',lost:'Perdida'}[s.kind]}</legend><label>Nombre de etapa ${i+1}<input data-stage-name="${i}" value="${esc(s.name)}" required maxlength="100"></label>${c.existing.has(s)?`<small>Código: ${esc(s.code)}</small>`:`<label>Código de nueva etapa<input data-stage-code="${i}" value="${esc(s.code)}" required pattern="[a-z][a-z0-9_]{0,39}" maxlength="40"></label>`}<button type="button" data-stages="up" data-index="${i}" ${i===0?'disabled':''} aria-label="Subir etapa ${i+1}">Subir</button><button type="button" data-stages="down" data-index="${i}" ${i===c.draft.length-1?'disabled':''} aria-label="Bajar etapa ${i+1}">Bajar</button></fieldset>`).join('');
  }
  function mount(root){
    const c=current;if(!c?.isCurrent())return;c.root=root;c.controller=new AbortController();const options={signal:c.controller.signal};rows(c);
    root.addEventListener('input',event=>{
      const input=event.target;if(input.dataset.stageName!==undefined)c.draft[Number(input.dataset.stageName)].name=input.value;
      if(input.dataset.stageCode!==undefined)c.draft[Number(input.dataset.stageCode)].code=input.value;
    },options);
    root.addEventListener('click',event=>{
      const button=event.target.closest('[data-stages]');if(!button||button.disabled||c.busy||!c.isCurrent())return;
      const action=button.dataset.stages;
      if(action==='refresh')return c.refresh();
      if(action==='add'){
        if(c.draft.length>=30){root.querySelector('#stages-feedback').textContent='El máximo es 30 etapas.';return;}
        let n=c.draft.length+1;while(c.draft.some(s=>s.code===`etapa_${n}`))n++;
        c.draft.push({code:`etapa_${n}`,name:'Nueva etapa',kind:'open',position:c.draft.length});
      }else{
        const i=Number(button.dataset.index),j=i+(action==='up'?-1:1);
        if(j<0||j>=c.draft.length)return;[c.draft[i],c.draft[j]]=[c.draft[j],c.draft[i]];
      }
      rows(c);
    },options);
    root.querySelector('#stages-form').addEventListener('submit',async event=>{
      event.preventDefault();if(c.busy||!c.isCurrent())return;
      c.busy=true;root.querySelectorAll('button,input').forEach(b=>b.disabled=true);const feedback=root.querySelector('#stages-feedback');feedback.textContent='Guardando etapas…';
      let saved=false;
      try{
        const stages=c.draft.map((s,i)=>({...s,position:i,name:s.name.trim()}));
        if(new Set(stages.map(s=>s.code)).size!==stages.length)throw new Error('Cada etapa debe tener un código distinto.');
        await c.api(`/organizations/${c.org}/crm/stages`,{method:'PUT',body:JSON.stringify({stages,expected_stages:c.original})});saved=true;
        if(c.isCurrent()){await c.refresh();if(current?.isCurrent())current.root.querySelector('#stages-feedback').textContent='Etapas guardadas correctamente.';}
      }catch(error){if(c.isCurrent())feedback.textContent=saved?'Guardadas, pero no se pudo actualizar la vista. Pulsa Actualizar.':error.status===409?'Las etapas cambiaron en otra sesión. Pulsa Actualizar y revisa los cambios antes de guardar.':error.message;}
      finally{c.busy=false;if(c.isCurrent()){root.querySelectorAll('button,input').forEach(b=>b.disabled=false);rows(c);}}
    },options);
  }
  return {render,mount,close,reset};
})();
