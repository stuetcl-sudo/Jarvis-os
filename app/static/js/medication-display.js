/* Read-only projection for the shared family display, never a plan editor. */
(() => {
  const root=document.querySelector('[data-medication-display="true"]');if(!root)return;
  const el=id=>document.getElementById(id);
  let data={today:'',people:[],entries:[]},selected='all',generation=0,receivedAt=0;
  function node(tag,text){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;}
  function select(id){selected=id;render();}
  function render(){
    if(selected!=='all'&&!data.people.some(p=>p.user_id===selected))selected='all';
    const group=el('medicationPeople');group.replaceChildren();
    for(const p of [{user_id:'all',display_name:'Alle'},...data.people]){const b=node('button',p.display_name);b.type='button';b.setAttribute('aria-pressed',String(p.user_id===selected));b.addEventListener('click',()=>select(p.user_id));group.append(b);}
    const entries=data.entries.filter(e=>selected==='all'||e.user_id===selected);
    const content=el('medicationDisplayContent');content.replaceChildren();
    for(const entry of entries){const card=node('section');card.className='pets-panel';card.append(node('h3',`${entry.person} · ${entry.name}`),node('p',`${entry.time} · ${{taken:'Registreret taget',skipped:'Sprunget over',unmarked:'Ikke registreret'}[entry.status]||'Ikke registreret'}`));content.append(card);}
    if(!entries.length)content.append(node('p','Ingen medicin planlagt i dag.'));
    window.dispatchEvent(new CustomEvent('jarvis:medication-summary',{detail:{today:data.today,people:data.people,entries,all_entries:data.entries,last_success_at:receivedAt,pending:entries.filter(e=>e.status==='unmarked').length,busy:false,selected_person:selected,select_person:select}}));
  }
  async function refresh(){const g=++generation;try{const r=await fetch('/api/family/medication/display',{credentials:'same-origin'});if(!r.ok)throw new Error('Dagens medicinoversigt kunne ikke hentes.');const value=await r.json();if(g!==generation)return;data=value;receivedAt=Date.now();el('medicationNotice').textContent='';render();}catch(e){if(g===generation){el('medicationNotice').textContent=e.message;window.dispatchEvent(new Event('jarvis:medication-error'));}}}
  refresh();setInterval(()=>{if(!document.hidden)refresh();},30000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
