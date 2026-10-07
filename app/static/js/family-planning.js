/* Shared family plans, with read-only snapshots from existing integration modules. */
(() => {
  const root=document.querySelector('[data-family-card="planning"]');if(!root)return;
  const byId=id=>document.getElementById(id);
  const zone=document.body.dataset.homeTimezone||'Europe/Copenhagen';
  const dayKey=value=>new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(value);
  const today=()=>dayKey(new Date());
  const nextDay=key=>{const d=new Date(`${key}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+1);return d.toISOString().slice(0,10);};
  const label=key=>new Intl.DateTimeFormat('da-DK',{weekday:'long',day:'numeric',month:'short',timeZone:'UTC'}).format(new Date(`${key}T12:00:00Z`));
  const symbols={'📅':'calendar','🍽️':'meal','👩‍🍳':'meal','🛒':'cart','🚗':'car','🎒':'bag','✏️':'edit'};
  const paths={calendar:'M4 5h16v16H4ZM4 10h16M8 3v4m8-4v4',meal:'M4 3v7q0 3 3 3t3-3V3M7 3v19M19 22V3q-5 4-5 10h5',cart:'M2 3h3l3 13h11l3-9H6M10 20h.1M18 20h.1',car:'M4 10l2-6h12l2 6M3 10h18v8H3ZM6 18v3m12-3v3M6 14h2m8 0h2',bag:'M8 5a4 4 0 0 1 8 0M5 7h14v15H5ZM8 13h8v6H8Z',edit:'m4 16 12-12 4 4L8 20H4ZM14 6l4 4'};
  function icon(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('planning-icon');const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('d',paths[name]);svg.append(p);return svg;}
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined){const symbol=Object.keys(symbols).find(s=>String(text).startsWith(s));if(symbol)n.append(icon(symbols[symbol]),document.createTextNode(String(text).slice(symbol.length).trimStart()));else n.textContent=text;}if(cls)n.className=cls;return n;};
  root.querySelectorAll('[data-planning-icon]').forEach(n=>n.prepend(icon(n.dataset.planningIcon)));

  const button=(text,fn)=>{const n=node('button',text);n.type='button';n.addEventListener('click',fn);return n;};
  for(const id of ['planningDialog','planningShoppingDialog','planningPeople']){const item=byId(id);item.classList.add('family-planning-dialog');document.body.append(item);}
  let state={days:[],can_edit:false,people:[]},calendar={status:'loading',events:[]},meals={status:'loading',days:[]},busy=false,editing=null,shoppingDay=null;
  async function api(path,method='GET',payload){
    const headers={};if(method!=='GET'){const session=await fetch('/api/auth/me');if(!session.ok)throw new Error('Log ind igen for at gemme.');headers['X-CSRF-Token']=(await session.json()).csrf_token;headers['Content-Type']='application/json';}
    const response=await fetch(path,{method,headers,credentials:'same-origin',...(payload===undefined?{}:{body:JSON.stringify(payload)})});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:'Kontrollér felterne og prøv igen.');}return response.json();
  }
  const sourceState=data=>({loading:'Henter…',authentication_required:'Log ind for at se oplysninger',hidden:'Skjult for denne rolle',not_configured:'Ikke tilsluttet',unavailable:'Kan ikke hentes lige nu'})[data.status];
  function eventsFor(day){return (calendar.events||[]).filter(e=>{if(e.all_day)return e.start<=day&&e.end>day;const start=new Date(e.start),end=new Date(e.end);if(!Number.isFinite(start.getTime())||!Number.isFinite(end.getTime()))return false;const endDay=dayKey(end),endTime=new Intl.DateTimeFormat('sv-SE',{timeZone:zone,hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).format(end);return dayKey(start)<=day&&(endDay>day||(endDay===day&&endTime!=='00:00:00'));}).sort((a,b)=>a.start.localeCompare(b.start));}
  function calendarState(day){return sourceState(calendar)||(calendar.range_end&&day>=calendar.range_end.slice(0,10)?'Uden for kalenderens hentede periode':null);}
  function mealMessage(day){return mealFor(day)||sourceState(meals)||((meals.days||[]).some(d=>d.date===day.date)?'Ikke planlagt':'Ingen madplan hentet for denne dag');}
  function mealFor(day){return day.meal||(meals.days||[]).find(d=>d.date===day.date)?.meals?.join(' · ')||'';}
  function edit(day){if(busy)return;editing=day.date;const form=byId('planningForm');for(const [key,value] of Object.entries(day)){if(form.elements.namedItem(key))form.elements.namedItem(key).value=Array.isArray(value)?value.join('\n'):value;}byId('planningDayTitle').textContent=label(day.date);byId('planningFormNotice').textContent='';byId('planningDialog').showModal();}
  async function openShopping(day){if(busy)return;shoppingDay=day.date;try{const shopping=await api('/api/family/shopping');const select=byId('planningShoppingForm').elements.namedItem('list_id');select.replaceChildren(...shopping.lists.map(list=>{const option=node('option',list.name);option.value=list.id;return option;}));byId('planningShoppingNotice').textContent=shopping.lists.length?'':'Opret først en liste under Indkøb.';byId('planningShoppingForm').querySelector('[type="submit"]').disabled=!shopping.lists.length;byId('planningShoppingDialog').showModal();}catch(e){byId('planningNotice').textContent=e.message;}}
  function render(){
    const grid=byId('familyWeek');grid.replaceChildren();
    for(const day of state.days){
      const card=node('section',undefined,'week-day');card.dataset.date=day.date;if(day.date===today())card.classList.add('week-today');
      card.append(node('h3',`${day.date===today()?'I dag · ':''}${label(day.date)}`));
      const appointments=node('div',undefined,'week-appointments');appointments.append(node('h4','📅 Aftaler'));
      const events=eventsFor(day.date);if(calendarState(day.date))appointments.append(node('p',calendarState(day.date)));else if(!events.length)appointments.append(node('p','Ingen hentede aftaler'));else for(const e of events){const time=e.all_day?'Hele dagen':new Intl.DateTimeFormat('da-DK',{timeZone:zone,hour:'2-digit',minute:'2-digit'}).format(new Date(e.start));appointments.append(node('p',`${time} · ${e.title||e.summary||'Aftale'}`));}if(calendar.stale)appointments.append(node('small','Tidligere hentet'));card.append(appointments);
      const food=node('div',undefined,'week-food');food.append(node('h4','🍽️ Aftensmad'),node('p',mealMessage(day)));
      if(day.cook)food.append(node('p',`👩‍🍳 ${day.cook} laver mad`));if(day.meal_notes)food.append(node('p',day.meal_notes));if(day.recipe_url){const a=node('a','Se opskrift ↗');a.href=day.recipe_url;a.target='_blank';a.rel='noopener noreferrer';food.append(a);}if(day.ingredients.length){const details=node('details');details.append(node('summary',`${day.ingredients.length} ingredienser`));const ul=node('ul');day.ingredients.forEach(i=>ul.append(node('li',i)));details.append(ul);food.append(details);if(state.can_edit)food.append(button('🛒 Til indkøb',()=>openShopping(day)));}card.append(food);
      if(day.pickup||day.pickup_notes||day.pickup_time)card.append(node('p',`🚗 ${[day.pickup_time,day.pickup?`${day.pickup} henter`:'Afhentning',day.pickup_notes].filter(Boolean).join(' · ')}`,'week-pickup'));
      if(day.reminders.length){const list=node('ul',undefined,'week-reminders');day.reminders.forEach(text=>list.append(node('li',`🎒 ${text}`)));card.append(list);}
      if(state.can_edit)card.append(button('✏️ Planlæg dagen',()=>edit(day)));grid.append(card);
    }
    byId('planningPeople').replaceChildren(...state.people.map(name=>{const option=node('option');option.value=name;return option;}));
    renderMealDetails();renderTomorrow();
    window.dispatchEvent(new CustomEvent('jarvis:planning-summary',{detail:{today:state.today,days:state.days}}));
  }
  const mealRoot=document.querySelector('[data-family-card="meal"]');let mealDetails=null;
  if(mealRoot){mealRoot.classList.add('has-family-planning');mealDetails=node('section',undefined,'family-meal-details');mealRoot.append(mealDetails);}
  function renderMealDetails(){if(!mealDetails)return;mealDetails.replaceChildren(node('h3','🍽️ Familiens madplan'));for(const day of state.days){const row=node('div',undefined,'meal-detail-day');row.append(node('strong',label(day.date)),node('p',mealMessage(day)));if(day.cook)row.append(node('p',`${day.cook} laver mad`));if(day.meal_notes)row.append(node('p',day.meal_notes));if(day.recipe_url){const a=node('a','Se opskrift ↗');a.href=day.recipe_url;a.target='_blank';a.rel='noopener noreferrer';row.append(a);}if(state.can_edit){row.append(button('✏️ Redigér',()=>edit(day)));if(day.ingredients.length)row.append(button('🛒 Ingredienser til indkøb',()=>openShopping(day)));}mealDetails.append(row);}}
  const overview=byId('dailyOverview');let tomorrowCard=null;
  if(overview){tomorrowCard=node('article',undefined,'daily-tile');tomorrowCard.dataset.module='tomorrow';const a=node('a',undefined,'daily-tile-heading');a.href='#uge';const symbol=node('span','🎒');symbol.setAttribute('aria-hidden','true');a.append(symbol,node('h2','Husk i morgen'),node('span','→'));tomorrowCard.append(a,node('div',undefined,'tomorrow-content'));overview.append(tomorrowCard);}
  function renderTomorrow(){if(!tomorrowCard)return;const content=tomorrowCard.querySelector('.tomorrow-content');content.replaceChildren();const day=state.days.find(d=>d.date===nextDay(today()));if(!day){content.append(node('p','Opdaterer morgendagens plan…'));return;}
    const items=[...day.reminders];if(day.pickup||day.pickup_notes||day.pickup_time)items.push(`🚗 ${[day.pickup_time,day.pickup?`${day.pickup} henter`:'Afhentning',day.pickup_notes].filter(Boolean).join(' · ')}`);
    for(const e of eventsFor(day.date)){const time=e.all_day?'Hele dagen':new Intl.DateTimeFormat('da-DK',{timeZone:zone,hour:'2-digit',minute:'2-digit'}).format(new Date(e.start));items.push(`📅 ${time} · ${e.title||e.summary||'Aftale'}`);}
    if(items.length){const list=node('ul');items.slice(0,3).forEach(text=>list.append(node('li',text)));content.append(list);if(items.length>3){const a=node('a',`Se alle ${items.length} i ugeoversigten →`);a.href='#uge';content.append(a);}}else content.append(node('p','Ingen huskeliste eller afhentning planlagt.'));
    if(calendarState(day.date))content.append(node('small',`Aftaler: ${calendarState(day.date)}`));else if(calendar.stale)content.append(node('small','Aftaler er tidligere hentet.'));
  }
  byId('planningCancel').addEventListener('click',()=>byId('planningDialog').close());byId('planningShoppingCancel').addEventListener('click',()=>byId('planningShoppingDialog').close());
  async function submit(form,notice,fn){if(busy)return;busy=true;const submitButton=form.querySelector('[type="submit"]');submitButton.disabled=true;notice.textContent='';try{await fn();}catch(e){notice.textContent=e.message;}finally{busy=false;submitButton.disabled=false;}}
  byId('planningForm').addEventListener('submit',e=>{e.preventDefault();submit(e.currentTarget,byId('planningFormNotice'),async()=>{const payload=Object.fromEntries(new FormData(e.currentTarget));for(const key of ['ingredients','reminders'])payload[key]=payload[key].split('\n').map(s=>s.trim()).filter(Boolean);await api(`/api/family/planning/${editing}`,'PUT',payload);await refresh();byId('planningDialog').close();});});
  byId('planningShoppingForm').addEventListener('submit',e=>{e.preventDefault();submit(e.currentTarget,byId('planningShoppingNotice'),async()=>{const result=await api(`/api/family/planning/${shoppingDay}/shopping`,'POST',{list_id:Number(new FormData(e.currentTarget).get('list_id'))});byId('planningShoppingNotice').textContent=`${result.added} varer tilføjet · ${result.already_present} stod allerede på listen.`;window.dispatchEvent(new Event('jarvis:shopping-changed'));});});
  let readId=0;
  async function refresh(){const id=++readId;try{const data=await api('/api/family/planning');if(id!==readId)return;state=data;byId('planningNotice').textContent='Fælles plan for hele familien · voksne kan redigere.';render();}catch(e){if(id===readId){byId('planningNotice').textContent=e.message;if(tomorrowCard&&!state.days.length)tomorrowCard.querySelector('.tomorrow-content').replaceChildren(node('p',e.message));}}}
  window.addEventListener('jarvis:calendar-updated',e=>{calendar=e.detail;render();});
  window.addEventListener('jarvis:meals-summary',e=>{meals=e.detail;render();});
  refresh();
  setInterval(refresh,30000);
})();
