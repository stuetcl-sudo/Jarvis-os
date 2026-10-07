(() => {
  const root = document.querySelector('[data-family-card="medication"]');
  if (!root) return;
  const el = (id) => document.getElementById(id);
  let data = {plans:[],people:[]}, editing = null, busy = false, generation = 0;
  function node(tag,text) {const n=document.createElement(tag); if(text!==undefined)n.textContent=text; return n;}
  function button(text,fn) {const b=node('button',text);b.type='button';b.addEventListener('click',fn);return b;}
  async function request(path='',method='GET',body) {
    const headers={};
    if(method!=='GET') {
      const session=await fetch('/api/auth/me',{credentials:'same-origin'});
      if(!session.ok)throw new Error('Log ind igen.');
      headers['X-CSRF-Token']=(await session.json()).csrf_token;headers['Content-Type']='application/json';
    }
    const r=await fetch(`/api/family/medication${path}`,{method,headers,credentials:'same-origin',...(body===undefined?{}:{body:JSON.stringify(body)})});
    if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(typeof e.detail==='string'?e.detail:'Kontrollér datoer, ugedage og klokkeslæt.');}
    return r.json();
  }
  async function refresh() {
    const g=++generation;
    try {const value=await request();if(g!==generation)return;data=value;render();el('medicationNotice').textContent='';}
    catch(e){if(g===generation)el('medicationNotice').textContent=`Kunne ikke opdatere. ${e.message}`;}
  }
  async function save(path,method,payload) {
    if(busy)return;busy=true;++generation;emitSummary();
    root.querySelectorAll('button').forEach(b=>b.disabled=true);
    try {await request(path,method,payload);await refresh();}
    catch(e){el('medicationNotice').textContent=e.message;}
    finally {busy=false;root.querySelectorAll('button').forEach(b=>b.disabled=false);emitSummary();}
  }
  function render() {
    const today=el('medicationToday'),plans=el('medicationPlans');today.replaceChildren();plans.replaceChildren();
    for(const p of data.plans) {
      const person=data.people.find(x=>x.user_id===p.user_id)?.display_name || 'Familiemedlem';
      if(p.due_today) {
        const card=node('section');card.className='pets-panel';card.append(node('h3',`${person} · ${p.name}`));
        if(p.instructions)card.append(node('p',p.instructions));
        for(const slot of p.times) {
          const record=p.records.find(x=>x.day===data.today&&x.slot===slot);
          const row=node('div');row.className='medication-slot';
          row.append(node('strong',`${slot} · ${{taken:'Registreret taget',skipped:'Sprunget over'}[record?.status]||'Ikke registreret'}`));
          row.append(button('Taget',()=>save(`/${p.id}/record`,'PUT',{revision:p.revision,day:data.today,slot,status:'taken'})),button('Sprunget over',()=>save(`/${p.id}/record`,'PUT',{revision:p.revision,day:data.today,slot,status:'skipped'})));
          if(record)row.append(button('Fortryd',()=>save(`/${p.id}/record`,'PUT',{revision:p.revision,day:data.today,slot,status:'unmarked'})));
          card.append(row);
        }
        today.append(card);
      }
      const card=node('section');card.className='pets-panel';
      card.append(node('h3',`${person} · ${p.name}`),node('p',`${p.active?'Aktiv':'Sat på pause'} · ${p.times.join(', ')} · ${p.weekdays.map(d=>['man','tir','ons','tor','fre','lør','søn'][d]).join(', ')}`),node('p',`${p.start_date}${p.end_date?` → ${p.end_date}`:''}`));
      if(p.instructions)card.append(node('p',p.instructions));
      card.append(button('Rediger',()=>open(p)),button('Slet plan',()=>{if(confirm(`Slet planen for ${p.name} og dens registreringer?`))save(`/${p.id}`,'DELETE');}));
      const history=node('details');history.append(node('summary',`${p.records.length} registreringer de seneste 30 dage`));
      for(const r of p.records){const who=data.people.find(x=>x.user_id===r.recorded_by)?.display_name||'Tidligere bruger';const original=JSON.parse(r.plan_snapshot||'{}');history.append(node('p',`${original.name||p.name}${original.instructions?` (${original.instructions})`:''} · ${r.day} kl. ${r.slot} · ${r.status==='taken'?'Taget':'Sprunget over'} · registreret af ${who}`));}
      card.append(history);plans.append(card);
    }
    if(!today.children.length)today.append(node('p','Ingen medicin planlagt i dag.'));
    if(!data.plans.length)plans.append(node('p','Ingen planer endnu.'));
    emitSummary();
  }
  function emitSummary() {
    const pending=data.plans.filter(p=>p.due_today).reduce((n,p)=>n+p.times.filter(t=>!p.records.some(r=>r.day===data.today&&r.slot===t)).length,0);
    const entries=data.plans.filter(p=>p.due_today).flatMap(p=>p.times.map(time=>({
      id:`${p.id}:${time}`,time,name:p.name,person:data.people.find(person=>person.user_id===p.user_id)?.display_name||'Familiemedlem',
      status:p.records.find(r=>r.day===data.today&&r.slot===time)?.status||'unmarked',
      change:(checked)=>save(`/${p.id}/record`,'PUT',{revision:p.revision,day:data.today,slot:time,status:checked?'taken':'unmarked'}),
    }))).sort((a,b)=>a.time.localeCompare(b.time)||a.id.localeCompare(b.id));
    window.dispatchEvent(new CustomEvent('jarvis:medication-summary',{detail:{today:data.today,pending,entries,busy}}));
  }
  function open(p=null) {
    editing=p;const f=el('medicationForm');f.reset();const select=f.elements.user_id;select.replaceChildren();const placeholder=node('option','Vælg familiemedlem');placeholder.value='';select.append(placeholder);
    for(const person of data.people){const option=node('option',person.display_name);option.value=person.user_id;select.append(option);}
    select.disabled=Boolean(p);select.value=p?.user_id||'';
    for(const k of ['name','instructions','start_date','end_date'])f.elements[k].value=p?.[k]??(k==='start_date'?data.today:'');
    f.elements.times.value=p?.times.join(', ')||'';f.elements.active.checked=p?.active??true;
    el('medicationWeekdays').replaceChildren();
    ['Mandag','Tirsdag','Onsdag','Torsdag','Fredag','Lørdag','Søndag'].forEach((name,i)=>{const label=node('label',name);label.className='pets-checkbox';const c=node('input');c.type='checkbox';c.name='weekday';c.value=String(i);c.checked=p?p.weekdays.includes(i):true;label.prepend(c);el('medicationWeekdays').append(label);});
    el('medicationFormNotice').textContent='';el('medicationDialog').showModal();
  }
  el('medicationAdd').addEventListener('click',()=>open());el('medicationCancel').addEventListener('click',()=>el('medicationDialog').close());
  el('medicationForm').addEventListener('submit',async e=>{
    e.preventDefault();if(busy)return;busy=true;++generation;const f=e.currentTarget,b=f.querySelector('[type="submit"]');b.disabled=true;
    try {await request(editing?`/${editing.id}`:'',editing?'PUT':'POST',{...(editing?{revision:editing.revision}:{}),user_id:f.elements.user_id.value,name:f.elements.name.value,instructions:f.elements.instructions.value,start_date:f.elements.start_date.value,end_date:f.elements.end_date.value||null,times:f.elements.times.value.split(',').map(t=>t.trim()),weekdays:[...f.querySelectorAll('[name="weekday"]:checked')].map(c=>Number(c.value)),active:f.elements.active.checked});el('medicationDialog').close();await refresh();}
    catch(err){el('medicationFormNotice').textContent=err.message;}
    finally{busy=false;b.disabled=false;}
  });
  refresh();setInterval(()=>{if(!document.hidden&&!busy)refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy)refresh();});
})();
