(() => {
  const root = document.querySelector('[data-family-card="pets"]');
  if (!root) return;
  const byId = (id) => document.getElementById(id);
  let state = { pets: [], can_edit: false, can_care: false };
  let selected = null;
  let editing = null;
  let reminderPet = null;
  let reminderEditing = null;
  let busy = false;
  let loading = false;
  let expensePet = null;
  let expenseGeneration = 0;
  let expenseMonth = null;
  const current = () => state.pets.find((pet) => pet.id === selected);
  const dateText = (date) => new Intl.DateTimeFormat('da-DK', {day:'numeric',month:'short',year:'numeric'}).format(new Date(`${date}T12:00:00`));
  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }
  function petIcon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'pet-icon'); svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS(svg.namespaceURI, 'use');
    use.setAttribute('href', `/static/icons/pets.svg#${name}`); svg.append(use); return svg;
  }
  function button(label, action) {
    const item = node('button', label);
    item.type = 'button'; item.addEventListener('click', action);
    return item;
  }
  async function request(path = '', method = 'GET', payload) {
    const headers = {};
    if (method !== 'GET') {
      const session = await fetch('/api/auth/me', {credentials:'same-origin'});
      if (!session.ok) throw new Error('Log ind igen for at gemme.');
      headers['X-CSRF-Token'] = (await session.json()).csrf_token;
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(`/api/family/pets${path}`, {
      method, headers, credentials:'same-origin',
      ...(payload === undefined ? {} : {body:JSON.stringify(payload)}),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Kontrollér felterne og prøv igen.');
    }
    return response.json();
  }
  async function refresh() {
    if (loading) return;
    loading = true;
    try {
      state = await request();
      if (!current()) selected = state.pets[0]?.id ?? null;
      render();
      byId('petsNotice').textContent = '';
    } catch (error) {
      byId('petsNotice').textContent = `Kunne ikke opdatere. ${error.message}`;
      if (!state.pets.length) byId('petsSummary').textContent = 'Kæledyr kunne ikke hentes.';
    } finally { loading = false; }
  }
  async function mutate(path, method, payload) {
    if (busy) return;
    busy = true;
    root.querySelectorAll('button').forEach((item) => { item.disabled = true; });
    try { await request(path, method, payload); await refresh(); }
    catch (error) { byId('petsNotice').textContent = error.message; }
    finally { busy = false; root.querySelectorAll('button').forEach((item) => { item.disabled = false; }); }
  }
  function careRequestId() {
    if(crypto.randomUUID)return crypto.randomUUID();
    const bytes=crypto.getRandomValues(new Uint8Array(16));bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
    const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join('');return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  function panel(title) {
    const item = node('section', undefined, 'pets-panel');
    item.append(node('h3', title)); return item;
  }
  function render() {
    const pet = current();
    byId('petsSummary').textContent = state.pets.length ? `${state.pets.length} kæledyr · ${dateText(state.today)}` : 'Tilføj familiens første kæledyr.';
    window.dispatchEvent(new CustomEvent('jarvis:pets-summary',{detail:{today:state.today,pets:state.pets}}));
    byId('petAdd').hidden = !state.can_edit;
    byId('petsPicker').replaceChildren(...state.pets.map((item) => {
      const pick = button(item.name, () => { selected = item.id; render(); });
      pick.setAttribute('aria-pressed', String(item.id === selected)); return pick;
    }));
    const content = byId('petsContent'); content.replaceChildren();
    if (!pet) {
      content.append(node('p', state.can_edit ? 'Start med navn og et foto. Resten kan udfyldes senere.' : 'En voksen kan tilføje jeres kæledyr.'));
      return;
    }
    const profile = panel(pet.name);
    if (pet.photo) {
      const photo = node('img', undefined, 'pet-photo'); photo.src = pet.photo; photo.alt = `Foto af ${pet.name}`; profile.prepend(photo);
    } else { const placeholder = node('div', undefined, 'pet-photo-placeholder'); placeholder.append(petIcon('paw')); profile.prepend(placeholder); }
    profile.append(node('p', pet.breed || 'Race / dyreart ikke angivet'));
    const details = node('dl', undefined, 'pet-details');
    for (const [label, value] of [['Født',pet.birth_date ? dateText(pet.birth_date) : 'Ikke angivet'], ['Vægt', pet.weight_kg ? `${pet.weight_kg.toLocaleString('da-DK')} kg` : 'Ikke angivet']]) {
      const row = node('div'); row.append(node('dt',label),node('dd',value)); details.append(row);
    }
    const chipRow = node('div');
    chipRow.append(node('dt', 'Chipnummer'));
    const chipValue = node('dd');
    if (pet.chip_number) {
      const disclosure = node('details', undefined, 'pet-chip');
      const toggle = node('summary', 'Vis chipnummer');
      disclosure.append(toggle, node('span', pet.chip_number));
      disclosure.addEventListener('toggle', () => { toggle.textContent = disclosure.open ? 'Skjul chipnummer' : 'Vis chipnummer'; });
      chipValue.append(disclosure);
    } else chipValue.textContent = 'Ikke angivet';
    chipRow.append(chipValue); details.append(chipRow);
    profile.append(details);
    const vet = node('section', undefined, 'pet-vet');
    vet.append(node('h4', 'Dyrlæge'));
    if (pet.vet_clinic) vet.append(node('p', pet.vet_clinic));
    if (pet.vet_name) vet.append(node('p', pet.vet_name));
    if (pet.vet_phone) {
      const number = pet.vet_phone.replace(/[^+0-9]/g, '');
      if (/^\+?\d{3,20}$/.test(number)) {
        const phone = node('a', pet.vet_phone, 'pet-vet-phone');
        phone.href = `tel:${number}`; vet.append(phone);
      } else vet.append(node('p', pet.vet_phone));
    }
    if (!pet.vet_name && !pet.vet_clinic && !pet.vet_phone) vet.append(node('p', 'Ingen dyrlæge angivet endnu.'));
    profile.append(vet);
    if (state.can_edit) {
      profile.append(button('Rediger profil', () => openProfile(pet)));
      profile.append(button('Slet kæledyr', () => {
        if (confirm(`Slet ${pet.name} og alle pasningsregistreringer og påmindelser?`)) mutate(`/${pet.id}`, 'DELETE');
      }));
    }
    const care = panel('I dag');
    const careTime = value => new Intl.DateTimeFormat('da-DK',{timeZone:document.body.dataset.homeTimezone||'Europe/Copenhagen',hour:'2-digit',minute:'2-digit'}).format(new Date(value));
    for (const [key,label,emoji] of [['food','Mad','food'],['water','Vand','water'],['walk','Gåtur','paw']]) {
      const count=pet.care_counts?.[key]??Number(Boolean(pet.care[key]));
      const row=node('div',undefined,'pet-care');
      const copy=node('span',label);copy.append(node('small',`${count} ${key==='walk'?(count===1?'tur':'ture'):'registreringer'} i dag${pet.care[key]?` · senest ${careTime(pet.care[key])}`:''}`));
      row.append(petIcon(emoji),copy);care.append(row);
      if(state.can_care) {
        row.append(button(key==='walk'?'+ Registrér tur':key==='food'?'+ Givet mad':'+ Givet vand',()=>mutate(`/${pet.id}/care/${key}/entries`,'POST',{day:state.today,request_id:careRequestId()})));
        const last=(pet.care_entries||[]).filter(e=>e.task===key).at(-1);
        if(last)care.append(button(`Fortryd seneste ${label.toLowerCase()}`,()=>mutate(`/${pet.id}/care/entries/${last.id}`,'DELETE')));
      }
    }
    const careHistory=node('details');careHistory.append(node('summary','Dagens registreringer'));
    for(const entry of pet.care_entries||[])careHistory.append(node('p',`${{food:'Mad',water:'Vand',walk:'Gåtur'}[entry.task]} · ${careTime(entry.completed_at)}`));
    care.append(careHistory);
    const health = panel('Sundhed & påmindelser');
    if (state.can_edit) health.append(button('+ Tilføj påmindelse', () => {
      openReminder(pet.id);
    }));
    if (!pet.reminders.length) health.append(node('p','Ingen påmindelser endnu.'));
    for (const reminder of pet.reminders) {
      const overdue = !reminder.completed && reminder.due_date < state.today;
      const row = node('article',undefined,`pet-reminder${overdue ? ' overdue' : ''}`);
      row.append(node('strong', reminder.title));
      const when = node('time',`${reminder.completed ? 'Klaret · ' : overdue ? 'Overskredet · ' : ''}${dateText(reminder.due_date)}`);
      when.dateTime = reminder.due_date; row.append(node('p', {vaccination:'Vaccination',medicine:'Medicin',vet:'Dyrlæge',other:'Andet'}[reminder.kind]),when);
      if (reminder.interval_unit !== 'none') row.append(node('p', `Gentages hver ${reminder.interval_count}. ${{days:'dag',weeks:'uge',months:'måned',years:'år'}[reminder.interval_unit] || ''}`));
      if (reminder.notes) row.append(node('p',reminder.notes));
      if (state.can_edit) {
        const actions = node('div',undefined,'pet-reminder-actions');
        actions.append(button(reminder.completed ? 'Fortryd klaret' : 'Markér klaret', () => mutate(`/${pet.id}/reminders/${reminder.id}`, 'PUT', {completed:!reminder.completed,occurrence_date:reminder.due_date})));
        actions.append(button('Rediger', () => openReminder(pet.id, reminder)));
        actions.append(button('Slet', () => {
          if (confirm(`Slet påmindelsen “${reminder.title}”?`)) mutate(`/${pet.id}/reminders/${reminder.id}`, 'DELETE');
        })); row.append(actions);
      }
      health.append(row);
    }
    content.append(profile,care,health);
    if (state.can_edit) {
      const economy = panel('Økonomi');
      economy.id = 'petEconomy'; content.append(economy);
      loadExpenses(pet.id, economy);
    }
  }
  function openReminder(petId, reminder = null) {
    reminderPet = petId; reminderEditing = reminder?.id ?? null;
    const form = byId('petReminderForm'); form.reset();
    if (reminder) for (const key of ['title','kind','due_date','notes','interval_unit','interval_count']) form.elements.namedItem(key).value = reminder[key];
    byId('petReminderTitle').textContent = reminder ? 'Rediger påmindelse' : 'Ny sundhedspåmindelse';
    byId('petReminderNotice').textContent = ''; byId('petReminderDialog').showModal();
  }
  function openProfile(pet = null) {
    editing = pet;
    const form = byId('petForm'); form.reset();
    for (const key of ['name','breed','birth_date','weight_kg','chip_number','vet_name','vet_clinic','vet_phone']) form.elements.namedItem(key).value = pet?.[key] ?? '';
    form.elements.namedItem('birth_date').max = state.today;
    byId('petDialogTitle').textContent = pet ? 'Rediger kæledyr' : 'Tilføj kæledyr';
    byId('petFormNotice').textContent = '';
    byId('petDialog').showModal();
  }
  async function photoData(file) {
    if (!['image/jpeg','image/png'].includes(file.type) || file.size > 8 * 1024 * 1024) throw new Error('Vælg JPEG eller PNG på højst 8 MB.');
    const bitmap = await createImageBitmap(file);
    try {
      const scale = Math.min(1,720 / Math.max(bitmap.width,bitmap.height));
      const canvas = document.createElement('canvas'); canvas.width = Math.max(1,Math.round(bitmap.width*scale)); canvas.height = Math.max(1,Math.round(bitmap.height*scale));
      const ctx = canvas.getContext('2d'); ctx.fillStyle = '#ffffff'; ctx.fillRect(0,0,canvas.width,canvas.height); ctx.drawImage(bitmap,0,0,canvas.width,canvas.height);
      const data = canvas.toDataURL('image/jpeg',.78);
      if (data.length > 400000) throw new Error('Billedet er for stort. Prøv et mindre foto.');
      return data;
    } finally { bitmap.close(); }
  }
  byId('petAdd').addEventListener('click', () => openProfile());
  root.querySelectorAll('[data-pets-close]').forEach((item) => item.addEventListener('click', () => byId(item.dataset.petsClose).close()));
  byId('petForm').addEventListener('submit', async (event) => {
    event.preventDefault(); if (busy) return; busy = true;
    const form = event.currentTarget;
    const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
    try {
      const data = Object.fromEntries(new FormData(form));
      data.birth_date = data.birth_date || null;
      data.weight_kg = data.weight_kg ? Number(data.weight_kg) : null;
      data.photo = byId('petRemovePhoto').checked ? '' : editing?.photo || '';
      const file = byId('petPhoto').files[0]; if (file) data.photo = await photoData(file);
      const result = await request(editing ? `/${editing.id}` : '', editing ? 'PUT' : 'POST',data);
      if (result.id) selected = result.id;
      byId('petDialog').close(); await refresh();
    } catch (error) { byId('petFormNotice').textContent = error.message; }
    finally { busy = false; submit.disabled = false; }
  });
  byId('petReminderForm').addEventListener('submit', async (event) => {
    event.preventDefault(); if (busy) return; busy = true;
    const form = event.currentTarget; const submit = form.querySelector('[type="submit"]'); submit.disabled = true;
    try {
      const payload=Object.fromEntries(new FormData(form));payload.interval_count=Number(payload.interval_count);
      await request(`/${reminderPet}/reminders${reminderEditing ? `/${reminderEditing}` : ''}`, reminderEditing ? 'PATCH' : 'POST',payload);
      byId('petReminderDialog').close(); await refresh();
    } catch (error) { byId('petReminderNotice').textContent = error.message; }
    finally { busy = false; submit.disabled = false; }
  });
  const expenseCategories = {food:'Foder',vet:'Dyrlæge',medicine:'Medicin',insurance:'Forsikring',care:'Pleje',other:'Andet'};
  const money = (ore) => new Intl.NumberFormat('da-DK',{style:'currency',currency:'DKK'}).format(ore/100);
  async function loadExpenses(petId, panel) {
    const generation=++expenseGeneration;
    try {
      const data=await request(`/${petId}/expenses`);
      if(generation!==expenseGeneration||!panel.isConnected||selected!==petId)return;
      const month=node('input');month.type='month';month.setAttribute('aria-label','Udgiftsmåned');month.value=expenseMonth||state.today.slice(0,7);
      const summary=node('div'),entries=node('div');
      const update=()=>{
        expenseMonth=month.value;const rows=data.expenses.filter(e=>e.day.startsWith(month.value));
        summary.replaceChildren(node('strong',`Registreret i måneden: ${money(rows.reduce((sum,e)=>sum+e.amount_ore,0))}`));
        for(const [key,label] of Object.entries(expenseCategories)){const sum=rows.filter(e=>e.category===key).reduce((n,e)=>n+e.amount_ore,0);if(sum)summary.append(node('p',`${label}: ${money(sum)}`));}
        entries.replaceChildren();
        for(const expense of rows){const row=node('div',undefined,'pet-expense-row');row.append(node('strong',`${expense.title} · ${money(expense.amount_ore)}`),node('p',`${dateText(expense.day)} · ${expenseCategories[expense.category]}`));if(expense.notes)row.append(node('p',expense.notes));row.append(button('Slet',()=>{if(confirm(`Slet udgiften “${expense.title}”?`))mutate(`/${petId}/expenses/${expense.id}`,'DELETE');}));entries.append(row);}
        if(!rows.length)entries.append(node('p','Ingen registrerede udgifter denne måned.'));
      };
      month.addEventListener('change',update);
      const history=node('details');history.append(node('summary','Vis månedens udgifter'),entries);
      panel.append(month,button('+ Registrér udgift',()=>{expensePet=petId;const f=byId('petExpenseForm');f.reset();f.elements.day.value=state.today;f.elements.day.max=state.today;byId('petExpenseNotice').textContent='';byId('petExpenseDialog').showModal();}),summary,history,node('p','Manuelt registrerede udgifter i DKK. Ingen bankforbindelse.','pets-footnote'));update();
    }catch(error){if(panel.isConnected)panel.append(node('p',`Udgifter kunne ikke hentes. ${error.message}`));}
  }
  byId('petExpenseForm').addEventListener('submit',async event=>{
    event.preventDefault();if(busy)return;busy=true;const f=event.currentTarget,b=f.querySelector('[type="submit"]');b.disabled=true;
    try {const payload=Object.fromEntries(new FormData(f));payload.amount_ore=Math.round(Number(payload.amount)*100);delete payload.amount;await request(`/${expensePet}/expenses`,'POST',payload);byId('petExpenseDialog').close();await refresh();}
    catch(error){byId('petExpenseNotice').textContent=error.message;}
    finally{busy=false;b.disabled=false;}
  });
  refresh();
  setInterval(() => { if (!document.hidden && !busy) refresh(); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !busy) refresh(); });
})();
