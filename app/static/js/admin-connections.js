let discoveredHomeAssistantEntities = [];

function ensureHomeAssistantPanel() {
  const section = document.querySelector('[data-admin-section="connections"]');
  if (!section || document.getElementById("homeAssistantSetupPanel")) return;

  const panel = element("section", "panel");
  panel.id = "homeAssistantSetupPanel";

  const heading = element("div", "panel-head");
  const headingText = element("div");
  headingText.append(
    element("h3", "", "Home Assistant"),
    element("p", "panel-help", "Forbind Jarvis til Home Assistant og vælg kalendere, lister, vejr, strøm og sensorer."),
  );
  const status = element("span", "pill", "Indlæser…");
  status.id = "homeAssistantSetupStatus";
  heading.append(headingText, status);

  const form = element("form", "connection-setup-form");
  form.id = "homeAssistantSetupForm";

  const urlLabel = element("label", "filter-label", "Home Assistant-adresse");
  urlLabel.htmlFor = "homeAssistantBaseUrl";
  const urlInput = element("input");
  urlInput.id = "homeAssistantBaseUrl";
  urlInput.name = "base_url";
  urlInput.type = "url";
  urlInput.placeholder = "Indtast Home Assistant-adressen";
  urlInput.autocomplete = "url";
  urlInput.required = true;
  urlLabel.append(urlInput);

  const tokenLabel = element("label", "filter-label", "Langtidstoken");
  tokenLabel.htmlFor = "homeAssistantToken";
  const tokenInput = element("input");
  tokenInput.id = "homeAssistantToken";
  tokenInput.name = "token";
  tokenInput.type = "password";
  tokenInput.placeholder = "Lad feltet være tomt for at beholde det gemte token";
  tokenInput.autocomplete = "new-password";
  tokenLabel.append(tokenInput);

  const help = element(
    "p",
    "panel-help",
    "Tokenet gemmes krypteret og bliver ikke vist igen. Forbindelsen testes, før den gemmes.",
  );

  const actions = element("div", "admin-header-actions");
  const testButton = element("button", "secondary", "Test forbindelse");
  testButton.type = "button";
  testButton.id = "testHomeAssistantButton";
  const discoverButton = element("button", "secondary", "Find entiteter");
  discoverButton.type = "button";
  discoverButton.id = "discoverHomeAssistantButton";
  const saveButton = element("button", "", "Gem forbindelse");
  saveButton.type = "submit";
  saveButton.id = "saveHomeAssistantButton";
  actions.append(testButton, discoverButton, saveButton);

  const result = element("div", "asset-detail muted", "Ingen entiteter hentet endnu.");
  result.id = "homeAssistantDiscoveryResult";
  result.setAttribute("aria-live", "polite");

  const selectorPanel = element("section", "entity-selector-panel");
  selectorPanel.id = "homeAssistantEntitySelectors";
  selectorPanel.hidden = true;
  selectorPanel.append(
    element("h4", "", "Vælg hvad Jarvis skal bruge"),
    element("p", "panel-help", "Jarvis viser almindelige navne, men gemmer de tekniske entitets-id’er sikkert på serveren."),
  );

  const selectorGrid = element("div", "content-grid two-columns");
  selectorGrid.id = "homeAssistantSelectorGrid";
  selectorPanel.append(selectorGrid);

  const saveSelectionsButton = element("button", "", "Gem valgte funktioner");
  saveSelectionsButton.type = "button";
  saveSelectionsButton.id = "saveHomeAssistantSelectionsButton";
  selectorPanel.append(saveSelectionsButton);

  form.append(urlLabel, tokenLabel, help, actions, result, selectorPanel);
  panel.append(heading, form);
  section.insertBefore(panel, section.querySelector(".panel"));
}

function homeAssistantPayload() {
  return {
    base_url: document.getElementById("homeAssistantBaseUrl").value.trim(),
    token: document.getElementById("homeAssistantToken").value.trim(),
  };
}

function setHomeAssistantBusy(busy) {
  [
    "testHomeAssistantButton",
    "discoverHomeAssistantButton",
    "saveHomeAssistantButton",
    "saveHomeAssistantSelectionsButton",
  ].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = busy;
  });
}

function entityLabel(item) {
  const parts = [item.name || item.entity_id];
  if (item.unit) parts.push(item.unit);
  parts.push(item.entity_id);
  return parts.join(" · ");
}

function matchingEntities(filter) {
  return discoveredHomeAssistantEntities.filter((item) => {
    if (filter.type && item.domain !== filter.type) return false;
    if (filter.deviceClass && item.device_class !== filter.deviceClass) return false;
    return true;
  });
}

function createSingleSelect(id, label, filter) {
  const wrapper = element("label", "filter-label", label);
  wrapper.htmlFor = id;
  const select = element("select");
  select.id = id;
  const empty = element("option", "", "Ikke valgt");
  empty.value = "";
  select.append(empty);
  matchingEntities(filter).forEach((item) => {
    const option = element("option", "", entityLabel(item));
    option.value = item.entity_id;
    select.append(option);
  });
  wrapper.append(select);
  return wrapper;
}

function createMultiSelect(id, label, filter) {
  const wrapper = element("label", "filter-label", label);
  wrapper.htmlFor = id;
  const select = element("select");
  select.id = id;
  select.multiple = true;
  select.size = Math.min(Math.max(matchingEntities(filter).length, 3), 8);
  matchingEntities(filter).forEach((item) => {
    const option = element("option", "", entityLabel(item));
    option.value = item.entity_id;
    select.append(option);
  });
  wrapper.append(select, element("small", "muted", "Hold Ctrl eller Cmd nede for at vælge flere."));
  return wrapper;
}

function renderHomeAssistantSelectors() {
  const grid = document.getElementById("homeAssistantSelectorGrid");
  if (!grid) return;
  grid.replaceChildren(
    createMultiSelect("haCalendarEntities", "Familiekalendere", { type: "calendar" }),
    createSingleSelect("haMealCalendar", "Madplan", { type: "calendar" }),
    createMultiSelect("haTaskEntities", "Opgaver og indkøbslister", { type: "todo" }),
    createSingleSelect("haWeatherEntity", "Vejr", { type: "weather" }),
    createSingleSelect("haElectricityPriceEntity", "Strømpris", { type: "sensor" }),
    createSingleSelect("haPowerEntity", "Aktuelt strømforbrug", { type: "sensor" }),
    createSingleSelect("haEnergyEntity", "Dagens energiforbrug", { type: "sensor" }),
    createMultiSelect("haTemperatureEntities", "Temperaturer", { type: "sensor", deviceClass: "temperature" }),
    createMultiSelect("haHumidityEntities", "Luftfugtighed", { type: "sensor", deviceClass: "humidity" }),
  );
  document.getElementById("homeAssistantEntitySelectors").hidden = false;
}

function selectedValues(id) {
  const select = document.getElementById(id);
  return select ? Array.from(select.selectedOptions).map((option) => option.value) : [];
}

function setSelectedValues(id, values) {
  const wanted = new Set(values || []);
  const select = document.getElementById(id);
  if (!select) return;
  Array.from(select.options).forEach((option) => {
    option.selected = wanted.has(option.value);
  });
}

function applyHomeAssistantEntitySettings(settings) {
  document.getElementById("haMealCalendar").value = settings.meal_calendar || "";
  document.getElementById("haWeatherEntity").value = settings.weather_entity || "";
  document.getElementById("haElectricityPriceEntity").value = settings.electricity_price_entity || "";
  document.getElementById("haPowerEntity").value = settings.power_entity || "";
  document.getElementById("haEnergyEntity").value = settings.energy_entity || "";
  setSelectedValues("haCalendarEntities", settings.calendar_entities);
  setSelectedValues("haTaskEntities", settings.task_entities);
  setSelectedValues("haTemperatureEntities", settings.temperature_entities);
  setSelectedValues("haHumidityEntities", settings.humidity_entities);
}

function homeAssistantEntitySettingsPayload() {
  return {
    calendar_entities: selectedValues("haCalendarEntities"),
    meal_calendar: document.getElementById("haMealCalendar").value,
    task_entities: selectedValues("haTaskEntities"),
    weather_entity: document.getElementById("haWeatherEntity").value,
    electricity_price_entity: document.getElementById("haElectricityPriceEntity").value,
    power_entity: document.getElementById("haPowerEntity").value,
    energy_entity: document.getElementById("haEnergyEntity").value,
    temperature_entities: selectedValues("haTemperatureEntities"),
    humidity_entities: selectedValues("haHumidityEntities"),
  };
}

async function loadHomeAssistantSummary() {
  ensureHomeAssistantPanel();
  try {
    const summary = await getJson("/api/admin/setup/home-assistant");
    document.getElementById("homeAssistantBaseUrl").value = summary.home_assistant_url || "";
    const status = document.getElementById("homeAssistantSetupStatus");
    status.textContent = summary.configured ? "Forbundet opsætning fundet" : "Ikke konfigureret";
    status.className = `pill ${summary.configured ? "ok" : "warning"}`;
  } catch (error) {
    showNotice(`Home Assistant-status kunne ikke hentes: ${error.message}`, "error", 0);
  }
}

async function testHomeAssistantConnection() {
  setHomeAssistantBusy(true);
  try {
    const result = await getJson("/api/admin/setup/home-assistant/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(homeAssistantPayload()),
    });
    showNotice(`Home Assistant er forbundet: ${result.message}`, "success");
  } catch (error) {
    showNotice(`Forbindelsen kunne ikke testes: ${error.message}`, "error", 0);
  } finally {
    setHomeAssistantBusy(false);
  }
}

async function saveHomeAssistantConnection(event) {
  event.preventDefault();
  setHomeAssistantBusy(true);
  try {
    const result = await getJson("/api/admin/setup/home-assistant/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(homeAssistantPayload()),
    });
    document.getElementById("homeAssistantToken").value = "";
    document.getElementById("homeAssistantBaseUrl").value = result.home_assistant_url || "";
    document.getElementById("homeAssistantSetupStatus").textContent = "Forbundet";
    showNotice("Home Assistant-forbindelsen er testet og gemt sikkert.", "success");
  } catch (error) {
    showNotice(`Forbindelsen kunne ikke gemmes: ${error.message}`, "error", 0);
  } finally {
    setHomeAssistantBusy(false);
  }
}

async function discoverHomeAssistantEntities() {
  setHomeAssistantBusy(true);
  const resultNode = document.getElementById("homeAssistantDiscoveryResult");
  resultNode.textContent = "Henter entiteter…";
  try {
    const [result, settings] = await Promise.all([
      getJson("/api/admin/setup/home-assistant/entities", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(homeAssistantPayload()),
      }),
      getJson("/api/admin/setup/home-assistant/entity-settings"),
    ]);
    discoveredHomeAssistantEntities = result.entities || [];
    renderHomeAssistantSelectors();
    applyHomeAssistantEntitySettings(settings);
    const counts = discoveredHomeAssistantEntities.reduce((acc, item) => {
      acc[item.domain] = (acc[item.domain] || 0) + 1;
      return acc;
    }, {});
    const summary = Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b, "da"))
      .slice(0, 8)
      .map(([kind, count]) => `${kind}: ${count}`)
      .join(" · ");
    resultNode.textContent = `${result.count} entiteter fundet${summary ? ` — ${summary}` : ""}`;
    showNotice("Home Assistant-entiteterne er hentet. Vælg nu, hvad Jarvis skal bruge.", "success");
  } catch (error) {
    resultNode.textContent = "Entiteterne kunne ikke hentes.";
    showNotice(`Entiteterne kunne ikke hentes: ${error.message}`, "error", 0);
  } finally {
    setHomeAssistantBusy(false);
  }
}

async function saveHomeAssistantSelections() {
  setHomeAssistantBusy(true);
  try {
    await getJson("/api/admin/setup/home-assistant/entity-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(homeAssistantEntitySettingsPayload()),
    });
    showNotice("De valgte Home Assistant-funktioner er gemt.", "success");
  } catch (error) {
    showNotice(`Valgene kunne ikke gemmes: ${error.message}`, "error", 0);
  } finally {
    setHomeAssistantBusy(false);
  }
}

function initializeHomeAssistantSetup() {
  ensureHomeAssistantPanel();
  document.getElementById("testHomeAssistantButton").addEventListener("click", testHomeAssistantConnection);
  document.getElementById("discoverHomeAssistantButton").addEventListener("click", discoverHomeAssistantEntities);
  document.getElementById("saveHomeAssistantSelectionsButton").addEventListener("click", saveHomeAssistantSelections);
  document.getElementById("homeAssistantSetupForm").addEventListener("submit", saveHomeAssistantConnection);
  loadHomeAssistantSummary();
}

initializeHomeAssistantSetup();
