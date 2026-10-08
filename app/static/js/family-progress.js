/* Shared server-backed rewards and voluntary check-ins. No inferred feelings. */
(() => {
  if(!document.querySelector('[data-family-card="rewards"]'))return;
  const el=id=>document.getElementById(id),node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const mood={good:'🙂 Godt',okay:'😐 Okay',hard:'🙁 Svært'},energy={high:'🔋 Meget overskud',low:'🔋 Lidt overskud',empty:'🪫 Tom for overskud'};
  let rewards={people:[]},wellbeing={people:[]},rewardPerson=null,rules=[],tasks=[],busy=false,generation=0;
  function button(text,action){const b=node('button',text);b.type='button';b.addEventListener('click',action);return b;}
  function compactChoice(field,value){
    const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('wellbeing-symbol');
    function shape(tag,attrs){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);svg.append(n);}
    if(field==='mood'){
      shape('circle',{cx:12,cy:12,r:9});shape('circle',{cx:9,cy:10,r:0.7,fill:'currentColor'});shape('circle',{cx:15,cy:10,r:0.7,fill:'currentColor'});
      shape('path',{d:{good:'M8 14 Q12 19 16 14',okay:'M8 15 H16',hard:'M8 17 Q12 12 16 17'}[value]});
    }else{
      shape('rect',{x:1,y:6,width:19,height:12,rx:2});shape('path',{d:'M22 10 V14'});
      for(let i=0;i<3;i++)shape('rect',{x:4+i*5,y:9,width:3,height:6,rx:0.5,fill:i<({high:3,low:1,empty:0}[value])?'currentColor':'none'});
    }
    return svg;
  }
  async function api(path,method='GET',body){const headers={};if(method!=='GET'){const r=await fetch('/api/auth/me');if(!r.ok)throw new Error('Log ind igen.');headers['X-CSRF-Token']=(await r.json()).csrf_token;headers['Content-Type']='application/json';}const r=await fetch('/api/family'+path,{method,headers,credentials:'same-origin',...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:'Kontrollér felterne.');return data;}
  const drafts=new Map(),queued=new Map(),saving=new Set(),errors=new Map(),views=new WeakMap();
  function personState(uid){return wellbeing.people.find(p=>p.user_id===uid);}
  function pick(uid,field,value){const p=personState(uid);if(!p?.can_write)return;const day=wellbeing.today;errors.delete(uid);const draft=drafts.get(uid)||{};draft[field]=value;draft.shared=true;drafts.set(uid,draft);queued.set(uid,{...queued.get(uid),day,[field]:value,shared:draft.shared});render();drain(uid);}
  async function drain(uid){if(saving.has(uid))return;saving.add(uid);render();try{while(queued.has(uid)){const patch=queued.get(uid);queued.delete(uid);await api(`/wellbeing/${uid}`,'PUT',patch);}}catch(e){queued.delete(uid);errors.set(uid,`Ikke gemt: ${e.message}`);}finally{saving.delete(uid);drafts.delete(uid);await refresh();}}
  async function clear(uid){if(saving.has(uid))return;saving.add(uid);render();try{await api(`/wellbeing/${uid}`,'DELETE');errors.delete(uid);}catch(e){errors.set(uid,e.message);}finally{saving.delete(uid);await refresh();}}
  function renderQuick(container,selectedId,compact=false){
    container.classList.toggle('wellbeing-compact',compact);
    let cards=views.get(container);if(!cards){cards=new Map();views.set(container,cards);}
    const people=selectedId?wellbeing.people.filter(p=>p.user_id===selectedId):wellbeing.people;const ids=new Set(people.map(p=>p.user_id));
    for(const [uid,view] of cards)if(!ids.has(uid)){view.card.remove();cards.delete(uid);}
    for(const p of people){let view=cards.get(p.user_id);if(!view){
      const card=node('section',undefined,'wellbeing-quick progress-person');card.dataset.personId=p.user_id;const title=node('h3',p.display_name);card.append(title);const choices=new Map();
      for(const [field,legend,labels] of [['mood','Humør',mood],['energy','Overskud',{high:'🔋 Meget',low:'🔋 Lidt',empty:'🪫 Tom'}]]){const group=node('fieldset');group.append(node('legend',legend));const row=node('div',undefined,'wellbeing-options');for(const [value,label] of Object.entries(labels)){const b=button(compact?'':label,()=>pick(p.user_id,field,value));if(compact)b.append(compactChoice(field,value),node('span',label.split(' ').slice(1).join(' ')));b.title=`${legend}: ${label}`;b.dataset.field=field;b.dataset.value=value;b.setAttribute('aria-label',`${p.display_name} · ${legend}: ${label}`);choices.set(field+':'+value,b);row.append(b);}group.append(row);card.append(group);}
      const status=node('p',undefined,'wellbeing-save-status');status.setAttribute('role','status');const remove=button('Fjern dagens svar',()=>clear(p.user_id));card.append(status,remove);view={card,title,choices,status,remove};cards.set(p.user_id,view);container.append(card);
    }
    view.title.textContent=p.display_name;const selected={...p.check_in,...drafts.get(p.user_id)};
    for(const [key,b] of view.choices){const [field,value]=key.split(':');b.setAttribute('aria-pressed',String(selected[field]===value));b.disabled=!p.can_write;}
    view.remove.hidden=wellbeing.shared_only||!p.can_write||!p.check_in;view.remove.disabled=saving.has(p.user_id);
    view.status.textContent=errors.get(p.user_id)|| (saving.has(p.user_id)?'Gemmer…':compact?(p.check_in?'Gemt ✓':p.can_write?'Tryk for at vælge':'Intet svar') :p.check_in?`Gemt i dag · delt med familien${!p.check_in.mood||!p.check_in.energy?' · det andet valg er frivilligt':''}`:p.can_write?'Vælg ét eller begge · gemmes automatisk':'Intet delt svar i dag');
    if(compact)view.remove.hidden=true;
    }
    if(!people.length){if(!container.querySelector('.wellbeing-empty'))container.append(node('p','Ingen synlige familiemedlemmer endnu.','wellbeing-empty'));}else container.querySelector('.wellbeing-empty')?.remove();
  }
  function emit(){window.dispatchEvent(new CustomEvent('jarvis:progress-summary',{detail:{rewards,wellbeing,quick_render:renderQuick}}));}
  async function action(path,method,body,notice){if(busy)return;busy=true;++generation;document.querySelectorAll('.progress-people button').forEach(b=>b.disabled=true);try{await api(path,method,body);await refresh();}catch(e){el(notice).textContent=e.message;}finally{busy=false;render();}}
  function render(){
    el('rewardsPeople').replaceChildren();
    for(const p of rewards.people){const card=node('section',undefined,'progress-person');card.append(node('h3',p.display_name));
      if(p.settings){card.append(node('strong',`⭐ ${p.balance} af ${p.settings.target} stjerner`),node('p',`Målet: ${p.settings.goal}`),node('small',`${p.earned} optjent i alt · ${p.spent} indløst`));const bar=node('progress');bar.max=p.settings.target;bar.value=Math.min(p.balance,p.settings.target);bar.setAttribute('aria-label','Stjerner til belønningen');card.append(bar);
        for(const rule of p.settings.rules){const completed=p.events.some(e=>e.day===rewards.today&&e.kind===rule.kind&&e.source===rule.source);const row=node('div',undefined,'progress-task');row.append(node('span',`${completed?'✓':'○'} ${rule.label} · +${rule.stars}`));if(rule.kind==='chore'&&rewards.can_complete&&(rewards.role!=='child'||rewards.self_id===p.user_id)){const b=button(completed?'Klaret i dag':'Færdig',()=>action(`/rewards/${p.user_id}/complete`,'POST',{source:rule.source,day:rewards.today},'rewardsNotice'));b.disabled=completed||busy;row.append(b);}else if(rule.kind==='routine'){const a=node('a','Åbn rutinen');a.href='#rutiner';row.append(a);}else if(rule.kind==='task'){const a=node('a','Åbn opgaver');a.href='#opgaver';row.append(a);}card.append(row);}
        if(rewards.can_manage){const b=button('Godkend belønning',()=>{if(confirm(`Indløs ${p.settings.target} stjerner til ${p.settings.goal}?`))action(`/rewards/${p.user_id}/redeem`,'POST',{goal:p.settings.goal,target:p.settings.target},'rewardsNotice');});b.disabled=p.balance<p.settings.target||busy;card.append(b);}
      }else card.append(node('p','Ingen aftale endnu. En voksen kan vælge opgaver og belønning.'));
      const badges=node('div',undefined,'progress-badges');for(const badge of p.badges){const b=node('span',`${badge.earned?'🏅':'☆'} ${badge.name} · ${Math.min(badge.progress,badge.target)}/${badge.target}`);b.className=badge.earned?'badge-earned':'badge-pending';badges.append(b);}card.append(badges);
      if(rewards.can_manage)card.append(button('Aftal stjerner',()=>openRewards(p)));el('rewardsPeople').append(card);
    }
    if(!rewards.people.length)el('rewardsPeople').append(node('p','Ingen synlige familiemedlemmer. En ejer kan tilføje dem eller ændre familievisning i Administration.'));
    renderQuick(el('wellbeingPeople'));
    emit();
  }
  async function refresh(){const g=++generation;const results=await Promise.allSettled([api('/rewards'),api('/wellbeing')]);if(g!==generation)return;for(let i=0;i<results.length;i++){const r=results[i];if(r.status==='fulfilled'){if(i===0)rewards=r.value;else wellbeing=r.value;el(i===0?'rewardsNotice':'wellbeingNotice').textContent='';}else el(i===0?'rewardsNotice':'wellbeingNotice').textContent=r.reason.message;}render();}
  function input(name,value,type='text'){const n=node('input');n.name=name;n.type=type;n.value=value;return n;}
  function renderRules(){el('rewardRules').replaceChildren();for(const rule of rules){const row=node('div',undefined,'reward-rule');const label=node('label','Navn');const name=input('label',rule.label);name.required=true;name.maxLength=120;name.addEventListener('input',()=>rule.label=name.value);label.append(name);row.append(label);
      if(rule.kind!=='chore'){const l=node('label',rule.kind==='routine'?'Rutine':'Eksisterende opgave');const select=node('select');const options=rule.kind==='routine'?[{value:'morning',label:'Morgenrutine'},{value:'evening',label:'Aftenrutine'}]:tasks;
        if(!options.some(o=>o.value===rule.source))options.unshift({value:rule.source,label:rule.label+' (tidligere valgt)'});
        for(const o of options){const opt=node('option',o.label);opt.value=o.value;select.append(opt);}select.value=rule.source;select.addEventListener('change',()=>rule.source=select.value);l.append(select);row.append(l);}
      const l=node('label','Stjerner');const stars=input('stars',rule.stars,'number');stars.min=1;stars.max=20;stars.required=true;stars.addEventListener('input',()=>rule.stars=Number(stars.value));l.append(stars);row.append(l,button('Fjern',()=>{rules=rules.filter(r=>r!==rule);renderRules();}));el('rewardRules').append(row);}}
  function openRewards(p){rewardPerson=p;rules=structuredClone(p.settings?.rules||[]);const f=el('rewardForm');f.reset();f.elements.goal.value=p.settings?.goal||'';f.elements.target.value=p.settings?.target||20;el('rewardFormNotice').textContent='';renderRules();el('rewardDialog').showModal();}
  el('rewardAddChore').addEventListener('click',()=>{if(rules.length>=40)return;rules.push({kind:'chore',source:`chore-${Date.now()}-${Math.random().toString(36).slice(2)}`,label:'',stars:1});renderRules();});
  el('rewardAddRoutine').addEventListener('click',()=>{if(rules.length>=40)return;rules.push({kind:'routine',source:'morning',label:'Morgenrutine',stars:2});renderRules();});
  el('rewardAddTask').addEventListener('click',async()=>{try{const data=await api('/tasks');tasks=(data.lists||[]).flatMap(l=>(l.items||[]).map(t=>({value:JSON.stringify([l.key,t.uid]),label:t.summary})));if(!tasks.length)throw new Error('Ingen tilgængelige opgaver. Du kan oprette en daglig opgave på tavlen.');if(rules.length>=40)return;rules.push({kind:'task',source:tasks[0].value,label:tasks[0].label,stars:1});renderRules();}catch(e){el('rewardFormNotice').textContent=e.message;}});
  el('rewardCancel').addEventListener('click',()=>el('rewardDialog').close());
  el('rewardForm').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;const b=e.currentTarget.querySelector('[type="submit"]');b.disabled=true;try{await api(`/rewards/${rewardPerson.user_id}`,'PUT',{goal:e.currentTarget.elements.goal.value,target:Number(e.currentTarget.elements.target.value),rules});el('rewardDialog').close();await refresh();}catch(err){el('rewardFormNotice').textContent=err.message;}finally{busy=false;b.disabled=false;render();}});
  window.addEventListener('jarvis:routines-changed',()=>{if(!busy)refresh();});window.addEventListener('jarvis:page-changed',e=>{if(['beloenninger','dagsform'].includes(e.detail)&&!busy)refresh();});window.addEventListener('jarvis:tasks-summary',()=>{if(!busy)refresh();});document.addEventListener('visibilitychange',()=>{if(!document.hidden&&!busy)refresh();});refresh();setInterval(()=>{if(!document.hidden&&!busy)refresh();},30000);
  window.JarvisDagsformLabels={mood,energy};
})();
