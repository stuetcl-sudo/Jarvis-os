(() => {
  const byId = (id) => document.getElementById(id);
  const owner = document.body.dataset.familyRole === 'owner';
  const shoppingRoot = document.querySelector('[data-family-card="shopping"]');
  const energyRoot = document.querySelector('[data-family-card="energy"]');
  const cameraRoot = document.querySelector('[data-family-card="cameras"]');
  if (!shoppingRoot && !energyRoot && !cameraRoot) return;
  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }
  function button(label, callback) {
    const item = node('button', label); item.type = 'button';
    item.addEventListener('click', callback); return item;
  }
  function external(url, label) {
    const link = node('a', label, 'module-button');
    link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; return link;
  }
  async function api(path, method = 'GET', payload) {
    const headers = {};
    if (method !== 'GET') {
      const session = await fetch('/api/auth/me', {credentials:'same-origin'});
      if (!session.ok) throw new Error('Log ind igen for at gemme.');
      headers['X-CSRF-Token'] = (await session.json()).csrf_token;
      headers['Content-Type'] = 'application/json';
    }
    const response = await fetch(path, {method, headers, credentials:'same-origin', ...(payload === undefined ? {} : {body:JSON.stringify(payload)})});
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(typeof data.detail === 'string' ? data.detail : 'Kontrollér felterne og prøv igen.');
    }
    return response.json();
  }
  document.querySelectorAll('[data-module-close]').forEach((item) => item.addEventListener('click', () => byId(item.dataset.moduleClose).close()));

  let shopping = {lists:[],can_manage:false,can_shop:false};
  let activeList = null;
  let listEditing = null;
  let itemEditing = null;
  let itemList = null;
  let shopBusy = false;
  let shopReadId = 0;
  const currentList = () => shopping.lists.find((item) => item.id === activeList);
  async function refreshShopping() {
    if (!shoppingRoot) return;
    const readId = ++shopReadId;
    try {
      const data = await api('/api/family/shopping');
      if (readId !== shopReadId) return;
      shopping = data;
      if (!currentList()) activeList = shopping.lists[0]?.id ?? null;
      renderShopping(); byId('shoppingNotice').textContent = '';
    } catch (error) { if (readId === shopReadId) byId('shoppingNotice').textContent = `Listen kunne ikke opdateres. ${error.message}`; }
  }
  async function shopWrite(path, method, payload) {
    if (shopBusy) return;
    shopBusy = true; ++shopReadId;
    shoppingRoot.querySelectorAll('button').forEach((item) => {item.disabled = true;});
    try {
      const result = await api(`/api/family/shopping${path}`, method, payload);
      await refreshShopping(); return result;
    } finally {
      shopBusy = false; shoppingRoot.querySelectorAll('button').forEach((item) => {item.disabled = false;});
    }
  }
  function shopAction(path, method, payload) {
    shopWrite(path,method,payload).catch((error) => {byId('shoppingNotice').textContent = error.message;});
  }
  function renderShopping() {
    const list = currentList();
    const pending = shopping.lists.reduce((total,item) => total + item.items.filter((i) => !i.done).length,0);
    byId('shoppingSummary').textContent = `${shopping.lists.length} liste${shopping.lists.length === 1 ? '' : 'r'} · ${pending} vare${pending === 1 ? '' : 'r'} mangler`;
    byId('shoppingAddList').hidden = !shopping.can_manage;
    byId('shoppingLists').replaceChildren(...shopping.lists.map((item) => {
      const link = button(item.name, () => {activeList = item.id; renderShopping();});
      link.setAttribute('aria-pressed',String(item.id === activeList)); return link;
    }));
    byId('shoppingTools').hidden = !list;
    byId('shoppingActiveTitle').textContent = list?.name || '';
    for (const id of ['shoppingRename','shoppingClear','shoppingDelete']) byId(id).hidden = !shopping.can_manage;
    byId('shoppingAddItem').hidden = !shopping.can_shop;
    const container = byId('shoppingItems'); container.replaceChildren();
    if (!list) {container.append(node('p',shopping.can_manage ? 'Opret den første liste til familiens indkøb.' : 'En voksen kan oprette en indkøbsliste.')); return;}
    const search = byId('shoppingSearch').value.trim().toLocaleLowerCase('da-DK');
    const items = list.items.filter((item) => `${item.name} ${item.quantity} ${item.category} ${item.note}`.toLocaleLowerCase('da-DK').includes(search));
    if (!items.length) container.append(node('p',search ? 'Ingen varer matcher søgningen.' : 'Listen er tom. Tilføj den første vare.'));
    let category = null;
    for (const item of items) {
      const label = item.done ? 'Købt' : item.category || 'Øvrige varer';
      if (category !== label) {container.append(node('h3',label,'shopping-category')); category = label;}
      const row = node('div',undefined,`shopping-row${item.done ? ' is-done' : ''}`);
      if (shopping.can_shop) {
        const check = button(item.done ? '✓' : '○', () => shopAction(`/${list.id}/items/${item.id}/state`,'PUT',{done:!item.done}));
        check.className = 'shopping-check'; check.setAttribute('aria-pressed',String(Boolean(item.done))); check.setAttribute('aria-label',`${item.name}: ${item.done ? 'fortryd købt' : 'markér købt'}`); row.append(check);
      }
      const copy = node('div',undefined,'shopping-copy'); copy.append(node('strong',item.name));
      if (item.quantity) copy.append(node('small',item.quantity));
      if (item.note) copy.append(node('small',item.note)); row.append(copy);
      if (shopping.can_manage) {
        row.append(button('Rediger', () => openItem(item)));
        row.append(button('Slet', () => {if (confirm(`Slet ${item.name}?`)) shopAction(`/${list.id}/items/${item.id}`,'DELETE');}));
      }
      container.append(row);
    }
  }
  function openList(edit = false) {
    listEditing = edit ? currentList()?.id : null;
    byId('shoppingListForm').reset();
    byId('shoppingListForm').elements.namedItem('name').value = edit ? currentList().name : '';
    byId('shoppingListTitle').textContent = edit ? 'Omdøb liste' : 'Ny liste';
    byId('shoppingListForm').querySelector('.module-form-notice').textContent = ''; byId('shoppingListDialog').showModal();
  }
  function openItem(item = null) {
    itemEditing = item?.id ?? null; itemList = activeList;
    const form = byId('shoppingItemForm'); form.reset();
    if (item) for (const key of ['name','quantity','category','note']) form.elements.namedItem(key).value = item[key];
    byId('shoppingItemTitle').textContent = item ? 'Rediger vare' : 'Tilføj vare';
    form.querySelector('.module-form-notice').textContent = ''; byId('shoppingItemDialog').showModal();
  }
  if (shoppingRoot) {
    byId('shoppingAddList').addEventListener('click', () => openList());
    byId('shoppingRename').addEventListener('click', () => openList(true));
    byId('shoppingAddItem').addEventListener('click', () => openItem());
    byId('shoppingSearch').addEventListener('input', renderShopping);
    byId('shoppingDelete').addEventListener('click', () => {if (confirm('Slet listen og alle dens varer?')) shopAction(`/${activeList}`,'DELETE');});
    byId('shoppingClear').addEventListener('click', () => {if (confirm('Fjern alle købte varer fra listen?')) shopAction(`/${activeList}/completed`,'DELETE');});
    byId('shoppingPrint').addEventListener('click', () => window.print());
    for (const [id,dialog] of [['shoppingListForm','shoppingListDialog'],['shoppingItemForm','shoppingItemDialog']]) {
      byId(id).addEventListener('submit', async (event) => {
        event.preventDefault(); if (shopBusy) return;
        const form = event.currentTarget; const data = Object.fromEntries(new FormData(form));
        try {
          let result;
          if (id === 'shoppingListForm') result = await shopWrite(listEditing ? `/${listEditing}` : '',listEditing ? 'PUT' : 'POST',data);
          else result = await shopWrite(`/${itemList}/items${itemEditing ? `/${itemEditing}` : ''}`,itemEditing ? 'PUT' : 'POST',data);
          if (id === 'shoppingListForm' && result?.id) {activeList = result.id; renderShopping();}
          byId(dialog).close();
        } catch (error) {form.querySelector('.module-form-notice').textContent = error.message;}
      });
    }
  }

  async function refreshEnergy() {
    if (!energyRoot) return;
    try {
      const data = await api('/api/family/energy');
      const valid = data.metrics.filter((item) => item.status === 'ok');
      byId('energySummary').textContent = data.status === 'not_configured' ? 'Vælg energisensorer for at komme i gang.' : `${valid.length} målinger tilgængelige`;
      byId('energyNotice').textContent = data.status === 'unavailable' ? 'Home Assistant svarer ikke. Værdierne er midlertidigt utilgængelige.' : data.status === 'not_configured' ? (owner ? 'Tilslut Home Assistant i Administration, og vælg derefter sensorer her.' : 'Ejeren kan tilslutte energisensorer.') : '';
      const select = byId('energyHistorySelect'); const previous = select.value;
      select.replaceChildren(...data.metrics.map((item) => {const option = node('option',item.label); option.value = item.key; return option;}));
      if ([...select.options].some((o) => o.value === previous)) select.value = previous;
      byId('energyMetrics').replaceChildren(...data.metrics.map((item) => {
        const card = node('section',undefined,'module-metric'); card.append(node('h3',item.label));
        card.append(node('strong',item.value === null ? '—' : `${item.value.toLocaleString('da-DK',{maximumFractionDigits:2})} ${item.unit}`));
        const status = {not_configured:'Sensor ikke valgt',unavailable:'Målingen kan ikke hentes',wrong_unit:'Sensorens enhed passer ikke til denne måling'}[item.status];
        card.append(node('small',status || (item.updated_at ? `Opdateret ${new Date(item.updated_at).toLocaleTimeString('da-DK',{hour:'2-digit',minute:'2-digit'})}` : 'Måling fra Home Assistant')));
        return card;
      }));
      if (document.body.dataset.appPage === 'energi') refreshHistory();
    } catch (error) {byId('energyNotice').textContent = error.message; byId('energyMetrics').replaceChildren(); byId('energySummary').textContent = 'Energidata kan ikke hentes.';}
  }
  let historyRequest = 0;
  async function refreshHistory() {
    const requestId = ++historyRequest;
    const container = byId('energyHistoryChart'); const status = byId('energyHistoryStatus');
    if (!container || !byId('energyHistorySelect').value) return;
    status.textContent = 'Henter historik…'; container.replaceChildren();
    try {
      const data = await api(`/api/family/energy/history/${encodeURIComponent(byId('energyHistorySelect').value)}`);
      if (requestId !== historyRequest) return;
      if (data.points.filter((p) => p.value !== null).length < 2) {
        status.textContent = data.status === 'not_configured' ? 'Vælg en sensor til denne måling.' : data.status === 'unavailable' ? 'Historik kan ikke hentes fra Home Assistant.' : 'Der er endnu ikke nok historik til en graf.'; return;
      }
      const points = data.points; const values = points.filter((p) => p.value !== null).map((p) => p.value);
      let min = Math.min(...values), max = Math.max(...values); if (min === max) {min -= 1; max += 1;}
      const first = new Date(points[0].time).getTime(), last = new Date(points[points.length-1].time).getTime();
      if (first === last) {status.textContent = 'Der er endnu ikke nok historik til en graf.'; return;}
      const svg = document.createElementNS('http://www.w3.org/2000/svg','svg');
      svg.setAttribute('viewBox','0 0 800 220'); svg.setAttribute('role','img'); svg.setAttribute('aria-label',`${data.label}, fra ${values[0]} til ${values[values.length-1]} ${data.unit}`);
      const segments = [[]];
      for (const p of points) {if (p.value === null) segments.push([]); else segments[segments.length-1].push(p);}
      for (const segment of segments) {
        const line = document.createElementNS(svg.namespaceURI,'polyline');
        line.setAttribute('points',segment.map((p) => `${20+(new Date(p.time).getTime()-first)/(last-first)*760},${200-(p.value-min)/(max-min)*180}`).join(' '));
        line.setAttribute('fill','none'); line.setAttribute('stroke','currentColor'); line.setAttribute('stroke-width','3'); line.setAttribute('vector-effect','non-scaling-stroke'); svg.append(line);
      }
      container.append(svg);
      status.textContent = `${data.label} · minimum ${Math.min(...values).toLocaleString('da-DK',{maximumFractionDigits:2})} ${data.unit} · maksimum ${Math.max(...values).toLocaleString('da-DK',{maximumFractionDigits:2})} ${data.unit}`;
      const times = node('div',undefined,'energy-history-times'); times.append(node('small',new Date(first).toLocaleString('da-DK')),node('small',new Date(last).toLocaleString('da-DK'))); container.append(times);
    } catch (error) {if (requestId === historyRequest) status.textContent = error.message;}
  }
  let cameras = [];
  let cameraLoaded = false;
  function snapshots() {
    if (document.body.dataset.appPage !== 'kamera') return;
    for (const img of byId('cameraGrid')?.querySelectorAll('img[data-snapshot]') || []) {
      const status = img.parentElement.querySelector('[data-image-status]');
      status.textContent = 'Henter snapshot…';
      img.hidden = false; img.src = `/api/family/cameras/${img.dataset.snapshot}/snapshot?t=${Date.now()}`;
    }
  }
  async function refreshCameras() {
    if (!cameraRoot) return;
    try {
      const data = await api('/api/family/cameras'); cameras = data.cameras;
      byId('camerasSummary').textContent = cameras.length ? `${cameras.filter((item) => item.status === 'available').length}/${cameras.length} tilgængelige via Home Assistant` : 'Ingen kameraer valgt endnu.';
      byId('cameraNotice').textContent = data.status === 'unavailable' ? 'Home Assistant svarer ikke.' : !cameras.length ? (owner ? 'Vælg kameraer under Opsæt kameraer.' : 'Ejeren kan tilføje kameraer.') : '';
      const scrypted = byId('scryptedLink'); scrypted.hidden = !data.scrypted_url; if (data.scrypted_url) scrypted.href = data.scrypted_url;
      byId('cameraGrid').replaceChildren(...cameras.map((item) => {
        const card = node('section',undefined,'module-camera'); card.append(node('h3',item.name));
        card.append(node('p',item.status === 'available' ? 'Tilgængeligt i Home Assistant' : 'Utilgængeligt i Home Assistant','module-camera-status'));
        const img = node('img'); img.alt = `Snapshot fra ${item.name}`; img.dataset.snapshot = String(item.id); img.hidden = true;
        const status = node('p','Åbn Kamera for at hente snapshot.','module-camera-status'); status.dataset.imageStatus = '';
        img.addEventListener('load', () => {status.textContent = `Snapshot hentet ${new Date().toLocaleTimeString('da-DK')}`;});
        img.addEventListener('error', () => {img.hidden = true; status.textContent = 'Snapshot kunne ikke hentes. Prøv Opdatér billeder.';});
        card.append(img,status);
        const actions = node('div',undefined,'module-camera-actions');
        if (item.live_url) actions.append(external(item.live_url,'Livevisning'));
        if (item.recordings_url) actions.append(external(item.recordings_url,'Optagelser'));
        card.append(actions); return card;
      }));
      cameraLoaded = true; snapshots();
    } catch (error) {byId('cameraNotice').textContent = error.message; byId('cameraGrid').replaceChildren(); cameraLoaded = false;}
  }
  let setup = null;
  let mode = null;
  let available = [];
  let configBusy = false;
  function field(label, input) {const wrap = node('label',label); wrap.append(input); return wrap;}
  function textInput(name,value,max=160) {const input = node('input'); input.name = name; input.value = value || ''; input.maxLength = max; return input;}
  function entitySelect(domain,value) {
    const select = node('select');
    const empty = node('option','Ikke valgt'); empty.value = ''; select.append(empty);
    const list = available.filter((item) => item.entity.startsWith(`${domain}.`));
    if (value && !list.some((item) => item.entity === value)) list.push({entity:value,name:'Gemt sensor',unit:''});
    for (const item of list) {const option = node('option',`${item.name}${item.unit ? ` · ${item.unit}` : ''} (${item.entity})`); option.value = item.entity; select.append(option);}
    select.value = value || ''; return select;
  }
  function addCamera(camera = null) {
    const box = node('fieldset',undefined,'module-camera-fields'); box.append(node('legend',camera?.name || 'Kamera'));
    const name = textInput('cameraName',camera?.name,80); name.required = true;
    const entity = entitySelect('camera',camera?.entity); entity.name = 'cameraEntity'; entity.required = true;
    const live = textInput('cameraLive',camera?.live_url,500); live.type = 'url';
    const recordings = textInput('cameraRecordings',camera?.recordings_url,500); recordings.type = 'url';
    box.append(field('Navn',name),field('Home Assistant-kamera',entity),field('Link til livevisning (valgfrit)',live),field('Link til optagelser (valgfrit)',recordings),button('Fjern kamera', () => box.remove()));
    byId('homeModuleFields').append(box);
  }
  async function openSetup(selectedMode) {
    mode = selectedMode; const fields = byId('homeModuleFields'); fields.replaceChildren();
    byId('homeConfigNotice').textContent = 'Henter opsætning…'; byId('homeConfigSave').disabled = true;
    byId('homeCameraAdd').hidden = mode !== 'cameras'; byId('homeModuleDialog').showModal();
    byId('homeModuleTitle').textContent = mode === 'energy' ? 'Vælg energisensorer' : 'Opsæt kameraer';
    byId('homeModuleHelp').textContent = mode === 'energy' ? 'Vælg sensorer med passende enheder. Til dagens tal skal du vælge dagsmålinger, der nulstilles ved midnat — ikke tællere for hele anlæggets levetid.' : 'Vælg op til 12 kameraer fra Home Assistant. Links åbnes direkte i din browser og skal kunne nås fra din enhed.';
    try {
      setup = await api('/api/admin/home-modules/config');
      available = [];
      try {available = (await api('/api/admin/home-modules/entities')).entities; byId('homeConfigNotice').textContent = '';}
      catch (error) {byId('homeConfigNotice').textContent = error.message;}
      if (mode === 'energy') {
        for (const item of setup.metrics) {const select = entitySelect('sensor',setup.energy[item.key]); select.name = item.key; fields.append(field(item.label,select));}
      } else {
        const scrypted = textInput('scrypted_url',setup.scrypted_url,500); scrypted.type = 'url'; fields.append(field('Scrypted-adresse (valgfrit)',scrypted));
        for (const camera of setup.cameras) addCamera(camera);
      }
      byId('homeConfigSave').disabled = false;
    } catch (error) {byId('homeConfigNotice').textContent = error.message;}
  }
  if (energyRoot) {
    byId('energyRefresh').addEventListener('click', refreshEnergy);
    byId('energyHistorySelect').addEventListener('change',refreshHistory);
    window.addEventListener('hashchange', () => {if (document.body.dataset.appPage === 'energi') refreshHistory();});
    byId('energySetup').hidden = !owner; byId('energySetup').addEventListener('click', () => openSetup('energy'));
  }
  if (cameraRoot) {
    byId('cameraRefresh').addEventListener('click', refreshCameras);
    byId('cameraSetup').hidden = !owner; byId('cameraSetup').addEventListener('click', () => openSetup('cameras'));
    window.addEventListener('hashchange', () => {if (document.body.dataset.appPage === 'kamera') cameraLoaded ? snapshots() : refreshCameras();});
  }
  if (byId('homeModuleForm')) {
    byId('homeCameraAdd').addEventListener('click', () => {
      if (byId('homeModuleFields').querySelectorAll('fieldset').length >= 12) {byId('homeConfigNotice').textContent = 'Der kan højst vælges 12 kameraer.'; return;} addCamera();
    });
    byId('homeModuleForm').addEventListener('submit', async (event) => {
      event.preventDefault(); if (configBusy || !setup) return;
      configBusy = true; byId('homeConfigSave').disabled = true;
      try {
        const latest = await api('/api/admin/home-modules/config');
        const payload = {energy:latest.energy,cameras:latest.cameras,scrypted_url:latest.scrypted_url};
        if (mode === 'energy') payload.energy = Object.fromEntries(setup.metrics.map((item) => [item.key,byId('homeModuleForm').elements.namedItem(item.key).value]));
        else {
          payload.scrypted_url = byId('homeModuleForm').elements.namedItem('scrypted_url').value;
          payload.cameras = [...byId('homeModuleFields').querySelectorAll('fieldset')].map((box) => ({name:box.querySelector('[name=cameraName]').value,entity:box.querySelector('[name=cameraEntity]').value,live_url:box.querySelector('[name=cameraLive]').value,recordings_url:box.querySelector('[name=cameraRecordings]').value}));
        }
        await api('/api/admin/home-modules/config','PUT',payload); byId('homeModuleDialog').close(); await Promise.allSettled([refreshEnergy(),refreshCameras()]);
      } catch (error) {byId('homeConfigNotice').textContent = error.message;}
      finally {configBusy = false; byId('homeConfigSave').disabled = false;}
    });
  }
  refreshShopping(); refreshEnergy(); refreshCameras();
  setInterval(() => {
    if (document.hidden) return;
    if (document.body.dataset.appPage === 'indkoeb' && !shopBusy) refreshShopping();
    if (document.body.dataset.appPage === 'energi') refreshEnergy();
  },30000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {if (!shopBusy) refreshShopping(); if (document.body.dataset.appPage === 'energi') refreshEnergy();}
  });
})();
