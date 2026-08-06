let discoveredHomeAssistantEntities = [];
let showTechnicalHomeAssistantEntities = false;

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
    element("p", "panel-help", "Vælg med almindelige afkrydsningsfelter. Tekniske entitets-id’er vises med mindre skrift."),
  );

  const pickerToolbar = element("div", "entity-picker-toolbar");
  const technicalToggle = element("button", "secondary", "Vis tekniske sensorer");
  technicalToggle.type = "button";
  technicalToggle.id = "toggleTechnicalEntitiesButton";
  technicalToggle.addEventListener("click", () => {
    showTechnicalHomeAssistantEntities = !showTechnicalHomeAssistantEntities;
    technicalToggle.textContent = showTechnicalHomeAssistantEntities
      ? "Skjul tekniske sensorer"
      : "Vis tekniske sensorer";
    const settings = homeAssistantEntitySettingsPayload();
    renderHomeAssistantSelectors();
    applyHomeAssistantEntitySettings(settings);
  });
  pickerToolbar.append(technicalToggle);
  selectorPanel.append(pickerToolbar);

  const selectorGrid = element("div", "entity-selector-grid");
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

function isLikelyTechnicalEntity(item) {
  const id = String(item.entity_id || "").toLowerCase();
  const name = String(item.name || "").toLowerCase();
  return [
    "localhost_",
    "acpitz",
    "processor_",
    "memory_use",
    "memory_free",
    "disk_use",
    "disk_free",
    "load_1m",
    "load_5m",
    "load_15m",
  ].some((part) => id.includes(part) || name.includes(part));
}

function matchingEntities(filter) {
  return discoveredHomeAssistantEntities.filter((item) => {
    if (filter.type && item.domain !== filter.type) return false;
    if (filter.deviceClass && item.device_class !== filter.deviceClass) return false;
    if (!showTechnicalHomeAssistantEntities && isLikelyTechnicalEntity(item)) return false;
    return true;
  });
}

function entityTitle(item) {
  return String(item.name || item.entity_id || "Ukendt");
}

function createSingleSelect(id, label, filter) {
  const card = element("section", "entity-picker-card");
  const fieldLabel = element("label", "filter-label", label);
  fieldLabel.htmlFor = id;
  const select = element("select");
  select.id = id;
  const empty = element("option", "", "Ikke valgt");
  empty.value = "";
  select.append(empty);
  matchingEntities(filter).forEach((item) => {
    const option = element("option", "", entityTitle(item));
    option.value = item.entity_id;
    option.title = item.entity_id;
    select.append(option);
  });
  fieldLabel.append(select);
  card.append(fieldLabel);
  return card;
}

function createCheckboxPicker(id, label, filter) {
  const card = element("section", "entity-picker-card");
  const title = element("h5", "", label);
  const searchLabel = element("label", "visually-hidden", `Søg i ${label}`);
  const search = element("input");
  search.type = "search";
  search.placeholder = `Søg i ${label.toLowerCase()}…`;
  searchLabel.append(search);

  const list = element("div", "entity-checkbox-list");
  list.id = id;
  list.dataset.picker = "true";
  const items = matchingEntities(filter);

  function render(query = "") {
    const needle = query.trim().toLowerCase();
    const visible = items.filter((item) => {
      const haystack = `${item.name || ""} ${item.entity_id || ""}`.toLowerCase();
      return !needle || haystack.includes(needle);
    });
    const previouslyChecked = new Set(
      Array.from(list.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value),
    );
    const rows = visible.map((item) => {
      const row = element("label", "entity-checkbox-row");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.value = item.entity_id;
      checkbox.checked = previouslyChecked.has(item.entity_id);
      const text = element("span", "entity-checkbox-text");
      text.append(
        element("strong", "", entityTitle(item)),
        element("small", "", item.entity_id),
      );
      row.append(checkbox, text);
      return row;
    });
    list.replaceChildren(...(rows.length ? rows : [element("p", "muted", "Ingen matchende entiteter.")]));
  }

  search.addEventListener("input", () => render(search.value));
  render();
  card.append(title, searchLabel, search, list);
  return card;
}

function renderHomeAssistantSelectors() {
  const grid = document.getElementById("homeAssistantSelectorGrid");
  if (!grid) return;
  grid.replaceChildren(
    createCheckboxPicker("haCalendarEntities", "Familiekalendere", { type: "calendar" }),
    createSingleSelect("haMealCalendar", "Madplan", { type: "calendar" }),
    createCheckboxPicker("haTaskEntities", "Opgaver og indkøbslister", { type: "todo" }),
    createSingleSelect("haWeatherEntity", "Vejr", { type: "weather" }),
    createSingleSelect("haElectricityPriceEntity", "Strømpris", { type: "sensor" }),
    createSingleSelect("haPowerEntity", "Aktuelt strømforbrug", { type: "sensor" }),
    createSingleSelect("haEnergyEntity", "Dagens energiforbrug", { type: "sensor" }),
    createCheckboxPicker("haTemperatureEntities", "Temperaturer", { type: "sensor", deviceClass: "temperature" }),
    createCheckboxPicker("haHumidityEntities", "Luftfugtighed", { type: "sensor", deviceClass: "humidity" }),
  );
  document.getElementById("homeAssistantEntitySelectors").hidden = false;
}

function selectedValues(id) {
  const picker = document.getElementById(id);
  if (!picker) return [];
  return Array.from(picker.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value);
}

function setSelectedValues(id, values) {
  const wanted = new Set(values || []);
  const picker = document.getElementById(id);
  if (!picker) return;
  picker.querySelectorAll('input[type="checkbox"]').forEach((input) => {
    input.checked = wanted.has(input.value);
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
    meal_calendar: document.getElementById("haMealCalendar")?.value || "",
    task_entities: selectedValues("haTaskEntities"),
    weather_entity: document.getElementById("haWeatherEntity")?.value || "",
    electricity_price_entity: document.getElementById("haElectricityPriceEntity")?.value || "",
    power_entity: document.getElementById("haPowerEntity")?.value || "",
    energy_entity: document.getElementById("haEnergyEntity")?.value || "",
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
    const visibleCount = discoveredHomeAssistantEntities.filter((item) => !isLikelyTechnicalEntity(item)).length;
    resultNode.textContent = `${visibleCount} relevante entiteter fundet. Tekniske sensorer er skjult som standard.`;
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

const integrationStateLabels = {
  connected: "Forbundet",
  unavailable: "Utilgængelig",
  not_configured: "Ikke konfigureret",
  degraded: "Kræver opmærksomhed",
  healthy: "Klar",
};

const supportedIntegrationNames = {
  home_assistant: "Home Assistant",
  scrypted: "Scrypted",
  electricity_prices: "Strømpriser",
  jarvis: "Jarvis",
};

const technicalKeyLabels = {
  configured: "Konfigureret",
  check: "Kontrol",
  warning_count: "Antal advarsler",
  response_class: "Svarstatus",
};

const technicalValueLabels = {
  configured: { true: "Ja", false: "Nej" },
  check: { api: "Home Assistant API", http: "Forbindelseskontrol", entity: "Sensorkontrol", health: "Systemkontrol", configuration: "Konfiguration" },
  response_class: {
    success: "Svar modtaget",
    authentication: "Login kræver opmærksomhed",
    not_found: "Ikke fundet",
    rate_limited: "Midlertidigt begrænset",
    server: "Tjenesten svarer med fejl",
    redirect: "Viderestilling afvist",
    response: "Uventet svar",
    transport: "Forbindelse mislykkedes",
    upstream: "Afhænger af en utilgængelig tjeneste",
    state: "Ugyldig sensorstatus",
  },
};

function safeTechnicalValue(key, value) {
  if (!Object.hasOwn(technicalKeyLabels, key)) return null;
  if (key === "warning_count" && Number.isInteger(value) && value >= 0) return String(value);
  if ((typeof value !== "string" && typeof value !== "boolean") || !Object.hasOwn(technicalValueLabels[key] || {}, String(value))) return null;
  return technicalValueLabels[key][String(value)];
}

function relativeChecked(value) {
  const checked = Date.parse(value);
  if (!Number.isFinite(checked)) return "Sidst opdateret: ukendt";
  const minutes = Math.max(0, Math.floor((Date.now() - checked) / 60000));
  if (minutes === 0) return "Sidst opdateret lige nu";
  if (minutes === 1) return "Sidst opdateret for 1 minut siden";
  return `Sidst opdateret for ${minutes} minutter siden`;
}

function integrationCard(item) {
  const card = element("article", "integration-status-card");
  const heading = element("h4", "", supportedIntegrationNames[item.key] || item.display_name);
  heading.append(element("span", `status ${safeClassToken(item.state)}`, integrationStateLabels[item.state] || "Ukendt"));
  const summary = element("p", "large-text", item.summary);
  const guidance = item.action_label && item.action_hint
    ? element("div", "integration-guidance")
    : null;
  if (guidance) guidance.append(element("strong", "", item.action_label), element("p", "panel-help", item.action_hint));
  const checked = element("time", "", relativeChecked(item.last_checked));
  checked.dateTime = item.last_checked;
  card.append(heading, summary);
  if (guidance) card.append(guidance);
  card.append(checked);
  if (item.technical_detail) {
    const details = element("details");
    details.append(element("summary", "", "Tekniske detaljer"));
    const list = element("dl", "access-list");
    Object.entries(item.technical_detail).forEach(([key, value]) => {
      const safeValue = safeTechnicalValue(key, value);
      if (safeValue === null) return;
      const row = element("div");
      row.append(element("dt", "", technicalKeyLabels[key]), element("dd", "", safeValue));
      list.append(row);
    });
    if (list.childElementCount > 0) {
      details.append(list);
      card.append(details);
    }
  }
  return card;
}

let integrationRefreshActive = false;
let hasValidIntegrationStatus = false;

async function loadIntegrationStatus({ manual = false } = {}) {
  if (integrationRefreshActive) return;
  const target = document.getElementById("integrationStatusCards");
  const button = document.getElementById("integrationRefreshButton");
  const feedback = document.getElementById("integrationRefreshFeedback");
  integrationRefreshActive = true;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  if (manual) feedback.textContent = "Opdaterer status…";
  try {
    const result = await getJson("/api/admin/integrations/status", { credentials: "same-origin" });
    target.replaceChildren(...result.integrations.map(integrationCard));
    updateIntegrationAttention(result.integrations);
    hasValidIntegrationStatus = true;
    if (manual) feedback.textContent = "Status er opdateret.";
  } catch (_error) {
    if (!hasValidIntegrationStatus) target.replaceChildren(element("p", "muted", "Integrationsstatus kunne ikke hentes."));
    if (manual) feedback.textContent = "Status kunne ikke opdateres. Prøv igen senere.";
  } finally {
    integrationRefreshActive = false;
    button.disabled = false;
    button.setAttribute("aria-busy", "false");
  }
}

initializeHomeAssistantSetup();
loadIntegrationStatus();
document.getElementById("integrationRefreshButton").addEventListener("click", () => loadIntegrationStatus({ manual: true }));
