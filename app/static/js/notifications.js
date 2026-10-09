(() => {
  const registration=window.isSecureContext&&'serviceWorker' in navigator?navigator.serviceWorker.register('/sw.js',{scope:'/'}).then(()=>navigator.serviceWorker.ready).catch(()=>null):Promise.resolve(null);
  const root=document.querySelector('[data-family-card="notifications"]');if(!root)return;
  const el=id=>document.getElementById(id),form=el('pushPreferences');
  const defaults={person_ids:[],medication:true,repeat_minutes:null,quiet_start:'22:00',quiet_end:'07:00',show_details:false};
  let data=null,user=null,currentId=null,browserSubscription=null,busy=false,installPrompt=null,audio=null,soundEnabled=false,summary=null,played={},storageKey='';
  const node=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
  const supported=()=>window.isSecureContext&&'PushManager' in window&&'Notification' in window&&'serviceWorker' in navigator;
  function store(value){try{localStorage.setItem(storageKey,JSON.stringify(value));}catch{el('pushSoundStatus').textContent='Browseren gemmer ikke lydvalg; aktivér igen efter genindlæsning.';}}
  function readLocal(){try{const value=JSON.parse(localStorage.getItem(storageKey)||'{}');return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}}
  function cleanPrefs(value){
    const result={...defaults,...(value&&typeof value==='object'?value:{})};
    result.person_ids=Array.isArray(result.person_ids)?result.person_ids.filter(p=>typeof p==='string'):[];
    result.repeat_minutes=[15,30,60].includes(result.repeat_minutes)?result.repeat_minutes:null;
    for(const key of ['quiet_start','quiet_end'])if(!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(result[key]))result[key]=defaults[key];
    return result;
  }
  async function api(path='',method='GET',payload){
    const headers={};if(method!=='GET'){const me=await fetch('/api/auth/me',{credentials:'same-origin'});if(!me.ok)throw new Error('Log ind igen.');headers['X-CSRF-Token']=(await me.json()).csrf_token;headers['Content-Type']='application/json';}
    const r=await fetch('/api/family/notifications'+path,{method,headers,credentials:'same-origin',...(payload===undefined?{}:{body:JSON.stringify(payload)})});const result=await r.json();
    if(!r.ok)throw new Error(typeof result.detail==='string'?result.detail:'Kontrollér felterne og prøv igen.');return result;
  }
  function prefs(){return {person_ids:[...el('pushPeople').querySelectorAll('input:checked')].map(i=>i.value),medication:form.elements.medication.checked,repeat_minutes:form.elements.repeat_minutes.value?Number(form.elements.repeat_minutes.value):null,quiet_start:form.elements.quiet_start.value,quiet_end:form.elements.quiet_end.value,show_details:form.elements.show_details.checked};}
  function renderPreferences(value){
    el('pushPeople').replaceChildren(node('legend','Hvem vil du have påmindelser om?'));
    for(const person of data.people){const label=node('label',person.display_name);label.className='pets-checkbox';const check=node('input');check.type='checkbox';check.value=person.user_id;check.checked=value.person_ids.includes(person.user_id);label.prepend(check);el('pushPeople').append(label);}
    for(const name of ['medication','show_details'])form.elements[name].checked=value[name];
    for(const name of ['quiet_start','quiet_end','repeat_minutes'])form.elements[name].value=value[name]??'';
  }
  function persistLocal(value=prefs()){
    store({preferences:value,id:currentId,soundEnabled,volume:el('pushVolume').value,played});
  }
  function controls(){
    el('pushEnable').disabled=busy||!data?.enabled||!data?.delivery_enabled||!data?.public_key||!supported();
    el('pushTest').hidden=!currentId;el('pushDisable').hidden=!currentId&&!browserSubscription;
    el('pushTest').disabled=busy;el('pushDisable').disabled=busy;el('pushSave').disabled=busy||!data;
  }
  async function refresh(fill=false){
    data=await api();const local=readLocal();
    if(!data.devices.some(d=>d.id===currentId))currentId=null;
    const device=data.devices.find(d=>d.id===currentId);
    if(fill){renderPreferences(cleanPrefs(device?.preferences||local.preferences));form.elements.name.value=device?.name||'Min telefon';}
    el('pushServerForm').hidden=!data.can_configure;
    if(data.can_configure){el('pushServerForm').elements.contact.value=(data.contact||'').replace(/^mailto:/,'');el('pushServerForm').elements.enabled.checked=data.enabled;}
    el('pushDevices').replaceChildren();
    for(const device of data.devices){const row=node('div');row.className='progress-buttons';const remove=node('button','Afmeld');remove.type='button';remove.addEventListener('click',()=>run(async()=>{await api(`/devices/${device.id}`,'DELETE');if(currentId===device.id){await browserSubscription?.unsubscribe();browserSubscription=null;currentId=null;}persistLocal();await refresh();el('pushNotice').textContent='Enheden er afmeldt.';}));row.append(node('span',device.name),remove);el('pushDevices').append(row);}
    if(!data.devices.length)el('pushDevices').append(node('p','Ingen telefoner tilmeldt endnu.'));
    el('pushDeviceStatus').textContent=!data.delivery_enabled?'Afsendelse er slået fra på denne server (fx staging). Lyd kan stadig afprøves.':currentId?'Denne browser er tilmeldt. Send en test og kontrollér telefonen.':!supported()?'Telefonbeskeder kræver HTTPS og en understøttet browser. På iPhone skal Jarvis åbnes fra hjemmeskærmen.':!data.enabled?'Ejeren skal aktivere telefonbeskeder for hjemmet først.':'Denne browser er ikke tilmeldt.';
    controls();
  }
  async function run(fn){if(busy)return;busy=true;controls();try{await fn();}catch(e){el('pushNotice').textContent=e.message;}finally{busy=false;controls();}}
  function applicationKey(value){const raw=atob(value.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-value.length%4)%4));return Uint8Array.from(raw,c=>c.charCodeAt(0));}
  async function registerDevice(){
    if(!browserSubscription)throw new Error('Tillad telefonbeskeder først.');
    const value=prefs();if(!value.person_ids.length)throw new Error('Vælg mindst én person.');
    const saved=await api('/devices','POST',{name:form.elements.name.value,subscription:browserSubscription.toJSON(),preferences:value});currentId=saved.id;persistLocal(value);await refresh();
  }
  el('pushEnable').addEventListener('click',()=>{
    if(busy||!supported())return;
    // Call permission directly from the user gesture (important for iOS).
    const permission=Notification.requestPermission();
    run(async()=>{if(await permission!=='granted')throw new Error('Beskeder blev ikke tilladt. Du kan ændre tilladelsen i enhedens indstillinger.');const worker=await registration;if(!worker)throw new Error('Jarvis kunne ikke registrere beskedtjenesten.');browserSubscription=await worker.pushManager.getSubscription()||await worker.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:applicationKey(data.public_key)});await registerDevice();el('pushNotice').textContent='Telefonen er tilmeldt. Send en testbesked.';});
  });
  form.addEventListener('submit',event=>{event.preventDefault();run(async()=>{persistLocal();if(currentId)await registerDevice();el('pushNotice').textContent=currentId?'Enhedens valg er gemt på Jarvis-serveren.':'Lydvalg er gemt på denne enhed. Tillad telefonbeskeder for at få push.';});});
  el('pushTest').addEventListener('click',()=>run(async()=>{const result=await api(`/devices/${currentId}/test`,'POST');el('pushNotice').textContent=result.message;}));
  el('pushDisable').addEventListener('click',()=>run(async()=>{if(currentId)await api(`/devices/${currentId}`,'DELETE');await browserSubscription?.unsubscribe();browserSubscription=null;currentId=null;persistLocal();await refresh();el('pushNotice').textContent='Telefonbeskeder er slået fra på denne enhed.';}));
  el('pushServerForm').addEventListener('submit',event=>{event.preventDefault();run(async()=>{await api('/config','PUT',{contact:'mailto:'+event.currentTarget.elements.contact.value,enabled:event.currentTarget.elements.enabled.checked});await refresh();el('pushNotice').textContent='Push-opsætningen er gemt.';});});
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();installPrompt=event;el('pwaInstall').hidden=false;});
  el('pwaInstall').addEventListener('click',async()=>{if(!installPrompt)return;await installPrompt.prompt();installPrompt=null;el('pwaInstall').hidden=true;});
  function soundState(){el('pushSoundStatus').textContent=soundEnabled?(audio?.state==='running'?'Lyd er aktiv, mens Jarvis er åben og synlig.':'Lyd er valgt. Tryk Aktivér lyd igen, hvis browseren kræver et nyt tryk.'):'Lyd er slået fra.';}
  function ding(){
    if(!audio||audio.state!=='running')throw new Error('Tryk Aktivér lyd for at tillade afspilning.');
    const oscillator=audio.createOscillator(),gain=audio.createGain(),start=audio.currentTime;
    oscillator.type='sine';oscillator.frequency.setValueAtTime(660,start);oscillator.frequency.setValueAtTime(880,start+0.12);
    gain.gain.setValueAtTime(0,start);gain.gain.linearRampToValueAtTime(Number(el('pushVolume').value),start+0.025);gain.gain.exponentialRampToValueAtTime(0.001,start+0.45);
    oscillator.connect(gain);gain.connect(audio.destination);oscillator.start(start);oscillator.stop(start+0.5);oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
  }
  el('pushSoundEnable').addEventListener('click',async()=>{
    try{const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio)throw new Error('Browseren understøtter ikke lyd.');audio||=new Audio();await audio.resume();ding();soundEnabled=true;persistLocal();soundState();}catch(e){el('pushSoundStatus').textContent=e.message;}
  });
  el('pushSoundDisable').addEventListener('click',()=>{soundEnabled=false;persistLocal();soundState();});
  el('pushVolume').addEventListener('change',()=>persistLocal());
  function soundTick(){
    if(!soundEnabled||document.hidden||!summary||summary.busy||Date.now()-(summary.last_success_at||0)>90000)return;
    const zone=document.body.dataset.homeTimezone||'Europe/Copenhagen',now=new Date();
    const day=new Intl.DateTimeFormat('sv-SE',{timeZone:zone,year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
    if(summary.today!==day)return;
    const clock=new Intl.DateTimeFormat('en-GB',{timeZone:zone,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(now);
    const value=cleanPrefs(readLocal().preferences),due=window.JarvisNotificationRules.due(summary.all_entries||summary.entries||[],day,clock,Date.now(),value,played);
    if(!due.length)return;
    try{ding();for(const entry of due)played[entry.key]=Date.now();played=Object.fromEntries(Object.entries(played).filter(([,time])=>Date.now()-time<7*86400000));persistLocal(value);}catch(e){el('pushSoundStatus').textContent=e.message;}
  }
  window.addEventListener('jarvis:medication-summary',event=>{summary=event.detail;soundTick();});
  window.addEventListener('jarvis:medication-error',()=>{summary=null;});
  setInterval(soundTick,30000);
  controls();
  (async()=>{
    try{const me=await fetch('/api/auth/me',{credentials:'same-origin'});if(!me.ok)return;user=await me.json();storageKey='jarvis.reminders.'+user.user_id;const local=readLocal();currentId=local.id||null;soundEnabled=Boolean(local.soundEnabled);played=local.played&&typeof local.played==='object'?local.played:{};el('pushVolume').value=['0.1','0.25','0.5'].includes(local.volume)?local.volume:'0.25';const worker=await registration;browserSubscription=await worker?.pushManager?.getSubscription();await refresh(true);el('pushNotice').textContent='';soundState();if(matchMedia('(display-mode: standalone)').matches||navigator.standalone)el('pwaStatus').textContent='Jarvis er åbnet som app på denne enhed.';}catch(e){el('pushNotice').textContent=e.message;}
  })();
})();
