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
  function panel(title) {
    const item = node('section', undefined, 'pets-panel');
    item.append(node('h3', title)); return item;
  }
  function render() {
    const pet = current();
    byId('petsSummary').textContent = state.pets.length ? `${state.pets.length} kæledyr · ${dateText(state.today)}` : 'Tilføj familiens første kæledyr.';
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
    for (const [key,label,emoji] of [['food','Mad','food'],['water','Vand','water'],['walk','Gåtur','paw']]) {
      const done = Boolean(pet.care[key]);
      const row = state.can_care ? button('', () => mutate(`/${pet.id}/care/${key}`, 'PUT', {done:!done,day:state.today})) : node('div');
      row.className = 'pet-care';
      const copy = node('span', label);
      copy.append(node('small', done ? 'Klaret i dag' : 'Ikke markeret endnu'));
      row.append(petIcon(emoji),copy,node('span',done ? '✓' : '○'));
      if (state.can_care) { row.setAttribute('aria-pressed',String(done)); row.setAttribute('aria-label',`${label}: ${done ? 'klaret, tryk for at fortryde' : 'markér klaret'}`); }
      care.append(row);
    }
    care.append(node('p', 'Sæt et flueben, når dagens pasning er klaret.', 'pets-footnote'));
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
      if (reminder.notes) row.append(node('p',reminder.notes));
      if (state.can_edit) {
        const actions = node('div',undefined,'pet-reminder-actions');
        actions.append(button(reminder.completed ? 'Fortryd klaret' : 'Markér klaret', () => mutate(`/${pet.id}/reminders/${reminder.id}`, 'PUT', {completed:!reminder.completed})));
        actions.append(button('Rediger', () => openReminder(pet.id, reminder)));
        actions.append(button('Slet', () => {
          if (confirm(`Slet påmindelsen “${reminder.title}”?`)) mutate(`/${pet.id}/reminders/${reminder.id}`, 'DELETE');
        })); row.append(actions);
      }
      health.append(row);
    }
    content.append(profile,care,health);
  }
  function openReminder(petId, reminder = null) {
    reminderPet = petId; reminderEditing = reminder?.id ?? null;
    const form = byId('petReminderForm'); form.reset();
    if (reminder) for (const key of ['title','kind','due_date','notes']) form.elements.namedItem(key).value = reminder[key];
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
      await request(`/${reminderPet}/reminders${reminderEditing ? `/${reminderEditing}` : ''}`, reminderEditing ? 'PATCH' : 'POST',Object.fromEntries(new FormData(form)));
      byId('petReminderDialog').close(); await refresh();
    } catch (error) { byId('petReminderNotice').textContent = error.message; }
    finally { busy = false; submit.disabled = false; }
  });
  refresh();
  setInterval(() => { if (!document.hidden && !busy) refresh(); }, 60000);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && !busy) refresh(); });
})();
