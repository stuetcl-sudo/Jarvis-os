/* Today's check-off on the shared display, never a plan editor. */
(() => {
  const root=document.querySelector('[data-medication-display="true"]');if(!root)return;
  const el=id=>document.getElementById(id);
  let data={today:'',people:[],entries:[]},selected='all',generation=0,receivedAt=0,busy=false;
  function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
  function select(id){if(busy)return;selected=id;render();}
  function button(text,fn){const b=node('button',text);b.type='button';b.disabled=busy;b.addEventListener('click',fn);return b;}
  function actionable(entry){return {...entry,change:checked=>save(entry,checked)};}
  async function save(entry,checked){
    if(busy||entry.read_only)return;
    const day=data.today;busy=true;++generation;render();
    try{
      const session=await fetch('/api/auth/me',{credentials:'same-origin'});
      if(!session.ok)throw new Error('Log ind igen.');
      const r=await fetch(`/api/family/medication/display/${entry.plan_id}/record`,{method:'PUT',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':(await session.json()).csrf_token},body:JSON.stringify({revision:entry.revision,day,slot:entry.time,status:checked?'taken':'unmarked'})});
      if(!r.ok){const error=await r.json().catch(()=>({}));throw new Error(typeof error.detail==='string'?error.detail:'Registreringen kunne ikke gemmes.');}
      await refresh();
    }catch(e){receivedAt=0;el('medicationNotice').textContent=e.message;window.dispatchEvent(new Event('jarvis:medication-error'));}
    finally{busy=false;render();}
  }
  function render(){
    if(selected!=='all'&&!data.people.some(p=>p.user_id===selected))selected='all';
    const group=el('medicationPeople');group.replaceChildren();
    for(const p of [{user_id:'all',display_name:'Alle'},...data.people]){const b=button(p.display_name,()=>select(p.user_id));b.setAttribute('aria-pressed',String(p.user_id===selected));group.append(b);}
    const all=data.entries.map(actionable),entries=all.filter(e=>selected==='all'||e.user_id===selected);
    const content=el('medicationDisplayContent');content.replaceChildren();
    for(const entry of entries){const card=node('section');card.className='pets-panel';card.append(node('h3',`${entry.person} · ${entry.name}`),node('p',`${entry.time} · ${{taken:'Registreret taget',skipped:'Sprunget over',unmarked:'Ikke registreret'}[entry.status]||'Ikke registreret'}`));if(!entry.read_only){card.append(button(entry.status==='taken'?'Fortryd registrering':'Registrér som taget',()=>save(entry,entry.status!=='taken')));}content.append(card);}
    if(!entries.length)content.append(node('p','Ingen medicin planlagt i dag.'));
    window.dispatchEvent(new CustomEvent('jarvis:medication-summary',{detail:{today:data.today,people:data.people,entries,all_entries:all,last_success_at:receivedAt,pending:entries.filter(e=>e.status==='unmarked').length,busy,selected_person:selected,select_person:select}}));
  }
  async function refresh(){const g=++generation;try{const r=await fetch('/api/family/medication/display',{credentials:'same-origin'});if(!r.ok)throw new Error('Dagens medicinoversigt kunne ikke hentes.');const value=await r.json();if(g!==generation)return;data=value;receivedAt=Date.now();el('medicationNotice').textContent='';render();}catch(e){if(g===generation){receivedAt=0;el('medicationNotice').textContent=e.message;window.dispatchEvent(new Event('jarvis:medication-error'));}}}
  refresh();setInterval(()=>{if(!document.hidden&&!busy)refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy)refresh();});
})();
