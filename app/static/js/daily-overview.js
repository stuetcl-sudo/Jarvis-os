/* Compact summaries; quick actions reuse existing authorized module writes. */
(() => {
  if(document.body.dataset.wallDashboard==='true')return;
  const shell=document.querySelector('.family-grid');if(!shell||!document.body.classList.contains('jarvis-app'))return;
  const overview=document.createElement('section');overview.id='dailyOverview';overview.className='daily-overview';overview.setAttribute('aria-label','Kun i dag');shell.before(overview);
  const primary=document.createElement('div');primary.className='daily-primary-grid';const status=document.createElement('div');status.className='daily-status-grid';overview.append(primary,status);
  const tiles=new Map();const cards=[...shell.querySelectorAll('[data-family-card]')];
  const definitions=[['routine','rutiner','Rutine nu'],['medication','medicin','Medicin i dag'],['calendar','kalender','Næste aftale'],['tasks','opgaver','Opgaver i dag'],['meal','madplan','Aftensmad'],['pets','kaeledyr','Kæledyr i dag'],['shopping','indkoeb','Indkøb'],['energy','energi','Energi i dag'],['cameras','kamera','Kamera'],['weather','vejr','Vejr nu']];
  for(const [card,hash,label] of definitions) {
    if(!cards.some(c=>c.dataset.familyCard===card)||!document.querySelector(`#appMenu a[href="#${hash}"]`))continue;
    const link=document.createElement('article');link.className='daily-tile';
    link.addEventListener('click',e=>{if(!e.target.closest('a,button,input,label'))location.hash=hash;});
    link.dataset.module=card;
    const header=document.createElement('a');header.href=`#${hash}`;header.className='daily-tile-heading';
    const symbol=document.querySelector(`#appMenu a[href="#${hash}"] svg`);
    if(symbol)header.append(symbol.cloneNode(true));
    const heading=document.createElement('h2');heading.textContent=label;header.append(heading);
    const arrow=document.createElement('span');arrow.textContent='→';arrow.setAttribute('aria-hidden','true');header.append(arrow);
    const metric=document.createElement('strong');metric.className='daily-tile-metric';metric.hidden=true;
    const summary=document.createElement('p');summary.textContent=document.body.dataset.familyRole==='anonymous'&&['calendar','meal','tasks'].includes(card)?'Log ind for at se dagens oplysninger':'Henter…';
    const actions=document.createElement('div');actions.className='daily-actions';actions.hidden=true;link.append(header,metric,summary,actions);(['shopping','energy','cameras','weather'].includes(card)?status:primary).append(link);tiles.set(card,{summary,metric,link,actions});
  }
  const zone=document.body.dataset.homeTimezone||'Europe/Copenhagen';
  const dayKey=d=>new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
  const today=()=>dayKey(new Date());
  const set=(key,text,metric='')=>{
    const tile=tiles.get(key);if(!tile)return;
    tile.summary.textContent=text;tile.metric.textContent=String(metric);tile.metric.hidden=metric==='';
  };
  const cache={};
  const unavailable={authentication_required:'Log ind for at se dagens oplysninger',not_configured:'Ikke tilsluttet',unavailable:'Kan ikke hentes lige nu'};
  function calendar(data) {
    if(unavailable[data.status]){set('calendar',unavailable[data.status]);return;}
    const events=(data.events||[]).filter(e=>{
      if(e.all_day)return e.start<=today()&&e.end>today();
      const start=new Date(e.start),end=new Date(e.end),now=new Date();
      return Number.isFinite(start.getTime())&&end>now&&(dayKey(start)===today()||start<now);
    }).sort((a,b)=>String(a.start).localeCompare(String(b.start)));
    if(!events.length){set('calendar','Ingen flere aftaler i dag','Fri');return;}
    const next=events[0];
    const time=next.all_day?'Hele dagen':new Intl.DateTimeFormat('da-DK',{timeZone:zone,hour:'2-digit',minute:'2-digit'}).format(new Date(next.start));
    set('calendar',`${next.summary||next.title||'Aftale'} · ${events.length} ${events.length===1?'aftale':'aftaler'} tilbage${data.status==='stale'?' · tidligere hentet':''}`,time);
  }
  function tasks(data) {
    if(unavailable[data.status]){set('tasks',unavailable[data.status]);return;}
    const items=(data.lists||[]).filter(l=>l.key!=='shopping'&&l.kind!=='shopping').flatMap(l=>l.items||[]).filter(i=>i.due&&(/^\d{4}-\d{2}-\d{2}$/.test(i.due)?i.due:Number.isFinite(new Date(i.due).getTime())?dayKey(new Date(i.due)):'')===today());
    set('tasks',items.length?`Tilbage i dag · ${items[0].summary}${data.status==='stale'?' · tidligere hentet':''}`:'Ingen opgaver med frist i dag',items.length);
  }
  function pets(data) {
    if(data.today!==today()){set('pets','Opdaterer dagens pasning…');return;}
    const care=data.pets.reduce((n,p)=>n+['food','water','walk'].filter(k=>!p.care[k]).length,0);
    const reminders=data.pets.reduce((n,p)=>n+p.reminders.filter(r=>!r.completed&&r.due_date===today()).length,0);
    set('pets',data.pets.length?`${data.pets.map(p=>p.name).join(', ')} · ${reminders} påmindelser i dag`:'Ingen kæledyr tilføjet',data.pets.length?`${care} tilbage`:'');
  }
  for(const [event,key,render] of [['calendar-updated','calendar',calendar],['tasks-summary','tasks',tasks],['pets-summary','pets',pets]]) {
    window.addEventListener(`jarvis:${event}`,e=>{cache[key]=e.detail;render(e.detail);});
  }
  window.addEventListener('jarvis:medication-summary',e=>{cache.medication=e.detail;renderMedication(e.detail);});
  window.addEventListener('jarvis:meals-summary',e=>{cache.meal=e.detail;renderMeal(e.detail);});
  function renderMedication(data) {
    const tile=tiles.get('medication');if(!tile)return;
    tile.medicationRows ||= new Map();
    const visible=data.today===today()?(data.entries||[]).slice(0,3):[];
    const keys=new Set(visible.map(entry=>entry.id));
    for(const [key,row] of tile.medicationRows)if(!keys.has(key)){row.label.remove();tile.medicationRows.delete(key);}
    for(const entry of visible) {
      let row=tile.medicationRows.get(entry.id);
      if(!row){
        const label=document.createElement('label');label.className='daily-check';
        const check=document.createElement('input');check.type='checkbox';
        const text=document.createElement('span');label.append(check,text);tile.actions.append(label);
        row={label,check,text};tile.medicationRows.set(entry.id,row);
        check.addEventListener('change',()=>{check.disabled=true;row.change(check.checked);});
      }
      row.change=entry.change;
      if(!data.busy)row.check.checked=entry.status==='taken';
      row.check.disabled=data.busy;
      row.check.setAttribute('aria-label',`${entry.status==='taken'?'Fortryd registrering af':'Registrér som taget:'} ${entry.name} for ${entry.person} kl. ${entry.time}`);
      row.text.textContent=`${entry.time} · ${entry.person} · ${entry.name}${entry.status==='taken'?' · taget':entry.status==='skipped'?' · sprunget over':''}`;
    }
    tile.moreLink ||= document.createElement('a');tile.moreLink.href='#medicin';
    if(data.today===today()&&data.entries?.length>3){tile.moreLink.textContent=`Vis alle ${data.entries.length} tidspunkter →`;tile.actions.append(tile.moreLink);}else tile.moreLink.remove();
    tile.actions.hidden=!visible.length;
    set('medication',data.today===today()?'Tidspunkter uden registrering i dag':'Opdaterer dagens plan…',data.today===today()?data.pending:'');
  }
  function renderMeal(data) {
    if(unavailable[data.status]){set('meal',unavailable[data.status]);return;}
    const meals=(data.days||[]).find(day=>day.date===today())?.meals;
    set('meal',meals?.length?`På menuen i dag${data.status==='stale'?' · tidligere hentet':''}`:'Ikke planlagt i dag',meals?.length?meals.join(' · '):'');
  }
  window.addEventListener('jarvis:shopping-summary',e=>{cache.shopping=e.detail;renderShopping(e.detail);});
  function renderShopping(data) {
    const count=data.lists.reduce((n,list)=>n+list.items.filter(i=>!i.done).length,0);
    set('shopping',`${count===1?'Vare':'Varer'} mangler · ${data.lists.length} ${data.lists.length===1?'liste':'lister'}`,count);
  }
  window.addEventListener('jarvis:energy-summary',e=>{cache.energy=e.detail;renderEnergy(e.detail);});
  function renderEnergy(data) {
    if(unavailable[data.status]){set('energy',unavailable[data.status]);return;}
    const valid=data.metrics.filter(m=>m.status==='ok');
    const main=valid.find(m=>m.key==='solar_today')||valid.find(m=>m.key==='consumption_today');
    if(!main){set('energy','Vælg en sensor for dagens produktion eller forbrug');return;}
    const other=valid.find(m=>m.key==='consumption_today'&&m.key!==main.key);
    set('energy',`${main.label}${other?` · forbrug ${other.value.toLocaleString('da-DK',{maximumFractionDigits:1})} ${other.unit}`:''}`,`${main.value.toLocaleString('da-DK',{maximumFractionDigits:1})} ${main.unit}`);
  }
  window.addEventListener('jarvis:cameras-summary',e=>{cache.cameras=e.detail;renderCameras(e.detail);});
  function renderCameras(data) {
    if(unavailable[data.status]){set('cameras',unavailable[data.status]);return;}
    if(!data.cameras.length){set('cameras','Ingen kameraer valgt endnu');return;}
    set('cameras','Tilgængelige i Home Assistant',`${data.cameras.filter(c=>c.status==='available').length}/${data.cameras.length}`);
  }
  function renderRoutine() {
    const tile=tiles.get('routine');if(!tile)return;
    const card=document.querySelector('[data-family-card="routine"]');tile.actions.replaceChildren();tile.actions.hidden=true;
    if(!card||card.hidden){set('routine','Ingen aktiv rutine lige nu');return;}
    const person=document.querySelector('#routinePersonSwitch [aria-pressed="true"]')?.textContent||'';
    const task=document.getElementById('routineTitle')?.textContent||'';
    const progress=document.getElementById('routineProgress')?.textContent||'';
    const name=document.getElementById('routineLabel')?.textContent||'Rutine';
    set('routine',`${person?`${person} · `:''}${name} · ${progress}`,task);
    const notice=document.getElementById('routineStaleNotice');
    if(notice&&!notice.hidden)tile.summary.textContent+=` · ${notice.textContent}`;
    const source=document.getElementById('routineComplete');
    if(source&&!source.hidden) {
      const complete=document.createElement('button');complete.type='button';complete.textContent='Færdig ✓';complete.disabled=source.disabled;complete.addEventListener('click',()=>{if(source.disabled||source.hidden||card.hidden)return;complete.disabled=true;source.click();});
      tile.actions.append(complete);tile.actions.hidden=false;
    }
    const people=[...document.querySelectorAll('#routinePersonSwitch button')];
    if(people.length>1){const group=document.createElement('div');group.className='daily-persons';group.setAttribute('role','group');group.setAttribute('aria-label','Vælg person til rutinen');for(const original of people){const b=document.createElement('button');b.type='button';b.textContent=original.textContent;b.disabled=original.disabled;b.setAttribute('aria-pressed',original.getAttribute('aria-pressed'));b.addEventListener('click',()=>{if(!original.disabled)original.click();});group.append(b);}tile.actions.append(group);tile.actions.hidden=false;}
  }
  function copy(key,ids) {
    for(const id of ids){const source=document.getElementById(id);if(source&&!source.hidden&&source.textContent.trim()){set(key,source.textContent.trim());return;}}
  }
  function refreshCopy() {
    renderRoutine();
    if(cache.meal)renderMeal(cache.meal);else copy('meal',['mealPlanState']);if(cache.shopping)renderShopping(cache.shopping);else copy('shopping',['shoppingSummary']);
    if(cache.energy)renderEnergy(cache.energy);else copy('energy',['energySummary']);
    if(cache.cameras)renderCameras(cache.cameras);else copy('cameras',['camerasSummary']);
    const weatherState=document.getElementById('weatherState');
    if(weatherState&&!weatherState.hidden)copy('weather',['weatherState']);
    else set('weather',document.getElementById('weatherCondition')?.textContent||'Vejr nu',document.getElementById('weatherTemperature')?.textContent||'');
    for(const key of ['calendar','tasks']) {
      const source=document.getElementById(key==='calendar'?'calendarState':'familyTasksState');
      if(source&&!source.hidden)set(key,source.textContent.trim());
    }
    const shoppingError=document.getElementById('shoppingNotice');if(shoppingError?.textContent.includes('kunne ikke opdateres'))set('shopping','Kan ikke opdateres lige nu');
    const cameraError=document.getElementById('cameraNotice');if(cameraError?.textContent&&cache.cameras?.cameras.length)set('cameras','Kan ikke opdateres lige nu');
    const petError=document.getElementById('petsNotice');if(petError?.textContent)set('pets','Kan ikke opdateres lige nu');
    const medError=document.getElementById('medicationNotice');if(medError?.textContent){set('medication','Kan ikke opdateres lige nu');const tile=tiles.get('medication');if(tile)tile.actions.querySelectorAll('input').forEach(c=>c.disabled=true);}
  }
  let queued=false;
  new MutationObserver(()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;refreshCopy();});}).observe(shell,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden','disabled','aria-pressed']});
  window.addEventListener('jarvis:page-changed',()=>{overview.hidden=document.body.dataset.appPage!=='overblik';});
  overview.hidden=document.body.dataset.appPage!=='overblik';refreshCopy();
  setInterval(()=>{if(cache.calendar)calendar(cache.calendar);if(cache.tasks)tasks(cache.tasks);if(cache.pets)pets(cache.pets);if(cache.meal)renderMeal(cache.meal);if(cache.medication)renderMedication(cache.medication);},30000);
})();
