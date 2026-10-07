/* Compact, read-only summaries. Full modules retain their own state and forms. */
(() => {
  if(document.body.dataset.wallDashboard==='true')return;
  const shell=document.querySelector('.family-grid');if(!shell||!document.body.classList.contains('jarvis-app'))return;
  const overview=document.createElement('section');overview.id='dailyOverview';overview.className='daily-overview';overview.setAttribute('aria-label','Kun i dag');shell.before(overview);
  const tiles=new Map();const cards=[...shell.querySelectorAll('[data-family-card]')];
  const definitions=[['calendar','kalender','Aftaler i dag'],['meal','madplan','Aftensmad'],['tasks','opgaver','Opgaver i dag'],['pets','kaeledyr','Kæledyr i dag'],['medication','medicin','Medicin i dag'],['shopping','indkoeb','Indkøb'],['energy','energi','Energi i dag'],['cameras','kamera','Kamera'],['weather','vejr','Vejr nu']];
  for(const [card,hash,label] of definitions) {
    if(!cards.some(c=>c.dataset.familyCard===card)||!document.querySelector(`#appMenu a[href="#${hash}"]`))continue;
    const link=document.createElement('a');link.href=`#${hash}`;link.className='daily-tile';
    const heading=document.createElement('h2');heading.textContent=label;
    const summary=document.createElement('p');summary.textContent=document.body.dataset.familyRole==='anonymous'&&['calendar','meal','tasks'].includes(card)?'Log ind for at se dagens oplysninger':'Henter…';
    const more=document.createElement('small');more.textContent='Åbn →';link.append(heading,summary,more);overview.append(link);tiles.set(card,summary);
  }
  const zone=document.body.dataset.homeTimezone||'Europe/Copenhagen';
  const dayKey=d=>new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
  const today=()=>dayKey(new Date());
  const set=(key,text)=>{if(tiles.has(key))tiles.get(key).textContent=text;};
  const cache={};
  const unavailable={authentication_required:'Log ind for at se dagens oplysninger',not_configured:'Ikke tilsluttet',unavailable:'Kan ikke hentes lige nu'};
  function calendar(data) {
    if(unavailable[data.status]){set('calendar',unavailable[data.status]);return;}
    const events=(data.events||[]).filter(e=>{
      if(e.all_day)return e.start<=today()&&e.end>today();
      const start=new Date(e.start),end=new Date(e.end),now=new Date();
      return Number.isFinite(start.getTime())&&end>now&&(dayKey(start)===today()||start<now);
    }).sort((a,b)=>String(a.start).localeCompare(String(b.start)));
    set('calendar',events.length?`${events.length} ${events.length===1?'aftale':'aftaler'} · ${events[0].all_day?'Hele dagen':new Intl.DateTimeFormat('da-DK',{timeZone:zone,hour:'2-digit',minute:'2-digit'}).format(new Date(events[0].start))} ${events[0].summary||events[0].title||'Aftale'}${data.status==='stale'?' · tidligere hentet':''}`:'Ingen flere aftaler i dag');
  }
  function tasks(data) {
    if(unavailable[data.status]){set('tasks',unavailable[data.status]);return;}
    const items=(data.lists||[]).filter(l=>l.key!=='shopping'&&l.kind!=='shopping').flatMap(l=>l.items||[]).filter(i=>i.due&&(/^\d{4}-\d{2}-\d{2}$/.test(i.due)?i.due:Number.isFinite(new Date(i.due).getTime())?dayKey(new Date(i.due)):'')===today());
    set('tasks',items.length?`${items.length} tilbage · ${items[0].summary}${data.status==='stale'?' · tidligere hentet':''}`:'Ingen opgaver med frist i dag');
  }
  function pets(data) {
    if(data.today!==today()){set('pets','Opdaterer dagens pasning…');return;}
    const care=data.pets.reduce((n,p)=>n+['food','water','walk'].filter(k=>!p.care[k]).length,0);
    const reminders=data.pets.reduce((n,p)=>n+p.reminders.filter(r=>!r.completed&&r.due_date===today()).length,0);
    set('pets',data.pets.length?`${care} pasningspunkter tilbage · ${reminders} påmindelser i dag`:'Ingen kæledyr tilføjet');
  }
  for(const [event,key,render] of [['calendar-updated','calendar',calendar],['tasks-summary','tasks',tasks],['pets-summary','pets',pets]]) {
    window.addEventListener(`jarvis:${event}`,e=>{cache[key]=e.detail;render(e.detail);});
  }
  window.addEventListener('jarvis:medication-summary',e=>{cache.medication=e.detail;set('medication',e.detail.today===today()?`${e.detail.pending} tidspunkter uden registrering i dag`:'Opdaterer dagens plan…');});
  window.addEventListener('jarvis:meals-summary',e=>{cache.meal=e.detail;renderMeal(e.detail);});
  function renderMeal(data) {
    if(unavailable[data.status]){set('meal',unavailable[data.status]);return;}
    const meals=(data.days||[]).find(day=>day.date===today())?.meals;
    set('meal',meals?.length?`${meals.join(' · ')}${data.status==='stale'?' · tidligere hentet':''}`:'Ikke planlagt i dag');
  }
  function copy(key,ids) {
    for(const id of ids){const source=document.getElementById(id);if(source&&!source.hidden&&source.textContent.trim()){set(key,source.textContent.trim());return;}}
  }
  function refreshCopy() {
    if(cache.meal)renderMeal(cache.meal);else copy('meal',['mealPlanState']);copy('shopping',['shoppingSummary']);copy('energy',['energySummary']);copy('cameras',['camerasSummary']);copy('weather',['weatherState','weatherTemperature']);
    for(const key of ['calendar','tasks']) {
      const source=document.getElementById(key==='calendar'?'calendarState':'familyTasksState');
      if(source&&!source.hidden)set(key,source.textContent.trim());
    }
    const petError=document.getElementById('petsNotice');if(petError?.textContent)set('pets','Kan ikke opdateres lige nu');
    const medError=document.getElementById('medicationNotice');if(medError?.textContent)set('medication','Kan ikke opdateres lige nu');
  }
  let queued=false;
  new MutationObserver(()=>{if(queued)return;queued=true;queueMicrotask(()=>{queued=false;refreshCopy();});}).observe(shell,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['hidden']});
  window.addEventListener('jarvis:page-changed',()=>{overview.hidden=document.body.dataset.appPage!=='overblik';});
  overview.hidden=document.body.dataset.appPage!=='overblik';refreshCopy();
  setInterval(()=>{if(cache.calendar)calendar(cache.calendar);if(cache.tasks)tasks(cache.tasks);if(cache.pets)pets(cache.pets);if(cache.meal)renderMeal(cache.meal);},30000);
})();
