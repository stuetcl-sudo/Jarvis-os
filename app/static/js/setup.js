let setupStep = 0;
let setupCsrfToken = "";
let setupSummary = null;
let setupEntities = [];
let showTechnicalSetupEntities = false;
let managedOnboardingState = "installation_requested";
let managedOnboardingPollTimer = null;
const MANAGED_ONBOARDING_POLL_MS = 3000;
const MANAGED_TRANSITIONAL_STATES = new Set(["installation_requested", "installing", "starting"]);
const setupSelections = {
  calendar_entities: new Set(),
  task_entities: new Set(),
  temperature_entities: new Set(),
  humidity_entities: new Set(),
};

async function setupJson(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  options.credentials = "same-origin";
  if (method !== "GET" && method !== "HEAD") {
    options.headers = { ...(options.headers || {}), "X-CSRF-Token": setupCsrfToken };
  }
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  const detail = body.detail || {};
  if (response.status === 401 && detail.code !== "authentication_failed") {
    window.location.assign(`/login?next=${encodeURIComponent("/setup")}`);
    throw new Error("Din session er udløbet");
  }
  if (!response.ok) {
    throw new Error(detail.message || (typeof detail === "string" ? detail : "") || response.statusText || "Anmodningen mislykkedes");
  }
  return body;
}

function showSetupNotice(message, tone = "success") {
  const notice = document.getElementById("setupNotice");
  notice.textContent = message;
  notice.className = `setup-notice ${tone}`;
  notice.hidden = false;
}

function createElement(tag, className = "", text = "") {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text) node.textContent = text;
  return node;
}

function ensureEntityPickerUi() {
  const step = document.querySelector('[data-step="2"]');
  if (!step || document.getElementById("setupEntitySelectorGrid")) return;
  const oldSummary = document.getElementById("setupContentSummary");
  if (oldSummary) oldSummary.remove();
  const oldActions = step.querySelector(".setup-actions");
  if (oldActions) oldActions.remove();
  const help = step.querySelector(".setup-help");
  if (help) help.textContent = "Vælg de kalendere, lister, sensorer og tjenester Jarvis skal bruge. Tekniske sensorer er skjult som standard.";
  const actions = createElement("div", "setup-actions left setup-picker-actions");
  const discover = createElement("button", "secondary", "Find entiteter");
  discover.type = "button";
  discover.id = "setupDiscoverEntitiesButton";
  const toggle = createElement("button", "secondary", "Vis tekniske sensorer");
  toggle.type = "button";
  toggle.id = "setupToggleTechnicalButton";
  actions.append(discover, toggle);
  const status = createElement("p", "setup-inline-status", "Ingen entiteter hentet endnu.");
  status.id = "setupEntityStatus";
  const grid = createElement("div", "entity-selector-grid");
  grid.id = "setupEntitySelectorGrid";
  grid.hidden = true;
  step.append(actions, status, grid);
  discover.addEventListener("click", discoverSetupEntities);
  toggle.addEventListener("click", () => {
    showTechnicalSetupEntities = !showTechnicalSetupEntities;
    toggle.textContent = showTechnicalSetupEntities ? "Skjul tekniske sensorer" : "Vis tekniske sensorer";
    renderSetupSelectors();
  });
}

function showStep(index) {
  setupStep = Math.max(0, Math.min(3, index));
  document.querySelectorAll("[data-step]").forEach((node) => {
    node.hidden = Number(node.dataset.step) !== setupStep;
  });
  document.querySelectorAll("[data-step-button]").forEach((button) => {
    const active = Number(button.dataset.stepButton) === setupStep;
    button.setAttribute("aria-current", active ? "step" : "false");
  });
  document.getElementById("setupBackButton").disabled = setupStep === 0;
  document.getElementById("setupNextButton").textContent = setupStep === 3 ? "Afslut opsætning" : "Gem og fortsæt";
  if (setupStep >= 2) refreshWizardSummary();
}

async function saveHomeStep() {
  await setupJson("/api/admin/setup/home", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      home_name: document.getElementById("setupHomeName").value.trim(),
      owner_name: document.getElementById("setupOwnerName").value.trim(),
      timezone: document.getElementById("setupTimezone").value,
    }),
  });
}

function homeAssistantPayload() {
  return {
    base_url: document.getElementById("setupHaUrl").value.trim(),
    token: document.getElementById("setupHaToken").value.trim(),
  };
}

async function testHomeAssistant(save = false) {
  const endpoint = save ? "/api/admin/setup/home-assistant/save" : "/api/admin/setup/home-assistant/test";
  const result = await setupJson(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(homeAssistantPayload()),
  });
  document.getElementById("setupHaStatus").textContent = save
    ? "Forbindelsen virker og er gemt sikkert."
    : "Forbindelsen til Home Assistant virker.";
  if (save) {
    document.getElementById("setupHaToken").value = "";
    document.getElementById("setupHaTokenStatus").textContent = "Et token er gemt krypteret.";
  }
  return result;
}

async function runHomeAssistantAction(save) {
  const testButton = document.getElementById("setupTestHaButton");
  const saveButton = document.getElementById("setupSaveHaButton");
  const nextButton = document.getElementById("setupNextButton");
  testButton.disabled = true;
  saveButton.disabled = true;
  nextButton.disabled = true;
  document.getElementById("setupHaStatus").textContent = save ? "Tester og gemmer…" : "Tester forbindelsen…";
  try {
    const result = await testHomeAssistant(save);
    showSetupNotice(save ? "Home Assistant-forbindelsen er gemt sikkert." : "Home Assistant-forbindelsen virker.");
    if (save && result.setup?.ready) window.location.assign("/admin");
    return result;
  } catch (error) {
    document.getElementById("setupHaStatus").textContent = error.message;
    showSetupNotice(error.message, "error");
    throw error;
  } finally {
    testButton.disabled = false;
    saveButton.disabled = false;
    nextButton.disabled = false;
  }
}

function selectedHomeAssistantChoice() {
  return document.getElementById("setupHaManagedChoice").checked ? "managed" : "existing";
}

function showHomeAssistantChoice() {
  const managed = selectedHomeAssistantChoice() === "managed";
  document.getElementById("setupHaExistingPanel").hidden = managed;
  document.getElementById("setupHaManagedPanel").hidden = !managed;
  if (managed) refreshManagedOnboardingStatus();
  else stopManagedOnboardingPolling();
}

function stopManagedOnboardingPolling() {
  if (managedOnboardingPollTimer !== null) window.clearTimeout(managedOnboardingPollTimer);
  managedOnboardingPollTimer = null;
}

function scheduleManagedOnboardingPoll() {
  stopManagedOnboardingPolling();
  if (document.hidden || !MANAGED_TRANSITIONAL_STATES.has(managedOnboardingState)) return;
  managedOnboardingPollTimer = window.setTimeout(refreshManagedOnboardingStatus, MANAGED_ONBOARDING_POLL_MS);
}

function renderManagedOnboarding(status) {
  managedOnboardingState = status.state;
  const panel = document.getElementById("setupManagedOnboarding");
  const openLink = document.getElementById("setupManagedOpenHomeAssistant");
  const steps = document.getElementById("setupManagedOnboardingSteps");
  const tokenLabel = document.getElementById("setupManagedTokenLabel");
  const tokenStatus = document.getElementById("setupManagedTokenStatus");
  const tokenActions = document.getElementById("setupManagedTokenActions");
  const publicUrlStatus = document.getElementById("setupManagedPublicUrlStatus");
  const canOpen = Boolean(status.home_assistant_url) && ["onboarding_required", "token_required", "connected"].includes(status.state);
  const needsGuidance = ["onboarding_required", "token_required"].includes(status.state);
  const needsToken = status.state === "token_required";
  panel.hidden = false;
  panel.dataset.state = status.state;
  document.getElementById("setupManagedOnboardingStatus").textContent = status.message;
  publicUrlStatus.textContent = status.public_url_message || "";
  publicUrlStatus.hidden = !status.public_url_message;
  openLink.hidden = !canOpen;
  if (canOpen) openLink.href = status.home_assistant_url;
  else openLink.removeAttribute("href");
  steps.hidden = !needsGuidance;
  tokenLabel.hidden = !needsToken;
  tokenStatus.hidden = !needsToken;
  tokenActions.hidden = !needsToken;
  tokenStatus.textContent = status.token_configured
    ? "Et gemt token kunne ikke valideres. Indsæt et nyt token."
    : "Tokenet vises eller udfyldes aldrig igen.";
  scheduleManagedOnboardingPoll();
}

async function refreshManagedOnboardingStatus() {
  stopManagedOnboardingPolling();
  if (document.hidden || selectedHomeAssistantChoice() !== "managed") return;
  try {
    renderManagedOnboarding(await setupJson("/api/admin/setup/home-assistant/managed/onboarding"));
  } catch (error) {
    managedOnboardingState = "failed";
    document.getElementById("setupManagedOnboardingStatus").textContent = error.message;
  }
}

function renderManagedInstallPlan(plan) {
  const summary = document.getElementById("setupManagedPlanSummary");
  const confirmation = document.getElementById("setupManagedConfirmation");
  const installButton = document.getElementById("setupManagedInstallButton");
  document.getElementById("setupManagedContainer").textContent = plan.container_name;
  document.getElementById("setupManagedImage").textContent = plan.image;
  document.getElementById("setupManagedVolume").textContent = `${plan.volume_name} → ${plan.config_mount_path}`;
  document.getElementById("setupManagedNetwork").textContent = `${plan.network_name}. ${plan.network_description}`;
  document.getElementById("setupManagedIsolation").textContent = plan.isolation_description;
  document.getElementById("setupManagedStatus").textContent = plan.message;
  summary.hidden = plan.state === "not_requested";
  confirmation.hidden = plan.state !== "ready_to_install";
  installButton.disabled = plan.installation_requested || !document.getElementById("setupManagedConfirmCheck").checked;
  if (plan.installation_requested) {
    document.getElementById("setupManagedStatus").textContent = "Installationen er anmodet og afventer den særskilte engangs-installer.";
  }
}

async function requestManagedInstallPlan() {
  const planButton = document.getElementById("setupManagedPlanButton");
  const nextButton = document.getElementById("setupNextButton");
  const choices = document.querySelectorAll('input[name="setupHaChoice"]');
  planButton.disabled = true;
  nextButton.disabled = true;
  choices.forEach((choice) => { choice.disabled = true; });
  document.getElementById("setupManagedStatus").textContent = "Opretter en sikker plan…";
  try {
    const plan = await setupJson("/api/admin/setup/home-assistant/managed/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    renderManagedInstallPlan(plan);
    showSetupNotice("Installationsplanen er oprettet. Home Assistant er ikke installeret eller startet.");
  } catch (error) {
    document.getElementById("setupManagedStatus").textContent = error.message;
    showSetupNotice(error.message, "error");
  } finally {
    planButton.disabled = false;
    nextButton.disabled = false;
    choices.forEach((choice) => { choice.disabled = false; });
  }
}

async function requestManagedInstallation() {
  const button = document.getElementById("setupManagedInstallButton");
  button.disabled = true;
  try {
    const result = await setupJson("/api/admin/setup/home-assistant/managed/install-request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    renderManagedInstallPlan(result);
    const hint = document.getElementById("setupManagedRunHint");
    hint.textContent = "Kør den faste engangs-installer på værten. Installationsanmodningen indeholder ingen Docker-parametre.";
    hint.hidden = false;
    showSetupNotice("Installationen er anmodet. Den særskilte engangs-installer skal nu køres af værten.");
    managedOnboardingState = "installation_requested";
    refreshManagedOnboardingStatus();
  } catch (error) {
    document.getElementById("setupManagedStatus").textContent = error.message;
    showSetupNotice(error.message, "error");
  }
}

async function runManagedTokenAction(save) {
  const testButton = document.getElementById("setupManagedTestTokenButton");
  const saveButton = document.getElementById("setupManagedSaveTokenButton");
  const nextButton = document.getElementById("setupNextButton");
  testButton.disabled = true;
  saveButton.disabled = true;
  nextButton.disabled = true;
  const token = document.getElementById("setupManagedHaToken").value.trim();
  const status = document.getElementById("setupManagedTokenStatus");
  status.textContent = save ? "Tester og gemmer tokenet…" : "Tester tokenet…";
  try {
    const result = await setupJson(`/api/admin/setup/home-assistant/managed/${save ? "save" : "test"}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    status.textContent = save ? "Tokenet er valideret og gemt sikkert." : "Tokenet virker.";
    if (save) {
      document.getElementById("setupManagedHaToken").value = "";
      managedOnboardingState = "connected";
      await refreshManagedOnboardingStatus();
      if (result.setup?.ready) window.location.assign("/admin");
      else if (setupStep === 1) showStep(2);
    }
    return result;
  } catch (error) {
    status.textContent = error.message;
    showSetupNotice(error.message, "error");
    throw error;
  } finally {
    testButton.disabled = false;
    saveButton.disabled = false;
    nextButton.disabled = false;
  }
}

function isTechnicalEntity(item) {
  const value = `${item.entity_id || ""} ${item.name || ""}`.toLowerCase();
  return ["localhost_", "acpitz", "processor_", "memory_use", "memory_free", "disk_use", "disk_free", "load_1m", "load_5m", "load_15m"].some((part) => value.includes(part));
}

function matchingSetupEntities(filter) {
  return setupEntities.filter((item) => {
    if (filter.domain && item.domain !== filter.domain) return false;
    if (filter.deviceClass && item.device_class !== filter.deviceClass) return false;
    if (!showTechnicalSetupEntities && isTechnicalEntity(item)) return false;
    return true;
  });
}

function setupEntityTitle(item) {
  return String(item.name || item.entity_id || "Ukendt");
}

function createSetupSingleSelect(id, label, filter) {
  const card = createElement("section", "entity-picker-card");
  const field = createElement("label", "filter-label", label);
  const select = createElement("select");
  select.id = id;
  const empty = createElement("option", "", "Ikke valgt");
  empty.value = "";
  select.append(empty);
  matchingSetupEntities(filter).forEach((item) => {
    const option = createElement("option", "", setupEntityTitle(item));
    option.value = item.entity_id;
    option.title = item.entity_id;
    select.append(option);
  });
  field.append(select);
  card.append(field);
  return card;
}

function createSetupCheckboxPicker(id, key, label, filter) {
  const card = createElement("section", "entity-picker-card");
  card.append(createElement("h5", "", label));
  const search = createElement("input");
  search.type = "search";
  search.placeholder = `Søg i ${label.toLowerCase()}…`;
  const list = createElement("div", "entity-checkbox-list");
  list.id = id;
  const items = matchingSetupEntities(filter);
  function render(query = "") {
    const needle = query.trim().toLowerCase();
    const visible = items.filter((item) => !needle || `${item.name || ""} ${item.entity_id || ""}`.toLowerCase().includes(needle));
    const rows = visible.map((item) => {
      const row = createElement("label", "entity-checkbox-row");
      const checkbox = createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = item.entity_id;
      checkbox.checked = setupSelections[key].has(item.entity_id);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) setupSelections[key].add(item.entity_id);
        else setupSelections[key].delete(item.entity_id);
      });
      const text = createElement("span", "entity-checkbox-text");
      text.append(createElement("strong", "", setupEntityTitle(item)), createElement("small", "", item.entity_id));
      row.append(checkbox, text);
      return row;
    });
    list.replaceChildren(...(rows.length ? rows : [createElement("p", "setup-help", "Ingen matchende entiteter.")]));
  }
  search.addEventListener("input", () => render(search.value));
  render();
  card.append(search, list);
  return card;
}

function readSingleValue(id) {
  return document.getElementById(id)?.value || "";
}

function currentEntitySettings() {
  return {
    calendar_entities: Array.from(setupSelections.calendar_entities),
    meal_calendar: readSingleValue("setupMealCalendar"),
    task_entities: Array.from(setupSelections.task_entities),
    weather_entity: readSingleValue("setupWeatherEntity"),
    electricity_price_entity: readSingleValue("setupElectricityPriceEntity"),
    power_entity: readSingleValue("setupPowerEntity"),
    energy_entity: readSingleValue("setupEnergyEntity"),
    temperature_entities: Array.from(setupSelections.temperature_entities),
    humidity_entities: Array.from(setupSelections.humidity_entities),
  };
}

function applyEntitySettings(settings) {
  ["calendar_entities", "task_entities", "temperature_entities", "humidity_entities"].forEach((key) => {
    setupSelections[key] = new Set(settings[key] || []);
  });
  const values = {
    setupMealCalendar: settings.meal_calendar,
    setupWeatherEntity: settings.weather_entity,
    setupElectricityPriceEntity: settings.electricity_price_entity,
    setupPowerEntity: settings.power_entity,
    setupEnergyEntity: settings.energy_entity,
  };
  Object.entries(values).forEach(([id, value]) => {
    const node = document.getElementById(id);
    if (node) node.value = value || "";
  });
}

function renderSetupSelectors(settings = currentEntitySettings()) {
  const grid = document.getElementById("setupEntitySelectorGrid");
  if (!grid) return;
  grid.replaceChildren(
    createSetupCheckboxPicker("setupCalendarEntities", "calendar_entities", "Familiekalendere", { domain: "calendar" }),
    createSetupSingleSelect("setupMealCalendar", "Madplan", { domain: "calendar" }),
    createSetupCheckboxPicker("setupTaskEntities", "task_entities", "Opgaver og indkøbslister", { domain: "todo" }),
    createSetupSingleSelect("setupWeatherEntity", "Vejr", { domain: "weather" }),
    createSetupSingleSelect("setupElectricityPriceEntity", "Strømpris", { domain: "sensor" }),
    createSetupSingleSelect("setupPowerEntity", "Aktuelt strømforbrug", { domain: "sensor" }),
    createSetupSingleSelect("setupEnergyEntity", "Dagens energiforbrug", { domain: "sensor" }),
    createSetupCheckboxPicker("setupTemperatureEntities", "temperature_entities", "Temperaturer", { domain: "sensor", deviceClass: "temperature" }),
    createSetupCheckboxPicker("setupHumidityEntities", "humidity_entities", "Luftfugtighed", { domain: "sensor", deviceClass: "humidity" }),
  );
  grid.hidden = false;
  applyEntitySettings(settings);
}

async function discoverSetupEntities() {
  const status = document.getElementById("setupEntityStatus");
  status.textContent = "Henter entiteter…";
  try {
    const [result, settings] = await Promise.all([
      setupJson("/api/admin/setup/home-assistant/entities", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(homeAssistantPayload()),
      }),
      setupJson("/api/admin/setup/home-assistant/entity-settings"),
    ]);
    setupEntities = result.entities || [];
    applyEntitySettings(settings);
    renderSetupSelectors(settings);
    const relevant = setupEntities.filter((item) => !isTechnicalEntity(item)).length;
    status.textContent = `${relevant} relevante entiteter fundet. Tekniske sensorer er skjult som standard.`;
    showSetupNotice("Entiteterne er hentet. Vælg nu, hvad Jarvis skal bruge.");
  } catch (error) {
    status.textContent = "Entiteterne kunne ikke hentes.";
    showSetupNotice(error.message, "error");
  }
}

async function saveEntitySettings() {
  await setupJson("/api/admin/setup/home-assistant/entity-settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentEntitySettings()),
  });
}

function summaryCard(title, value) {
  const card = createElement("div", "summary-card");
  card.append(createElement("strong", "", title), createElement("span", "", value));
  return card;
}

async function refreshWizardSummary() {
  setupSummary = await setupJson("/api/admin/setup/summary");
  const final = document.getElementById("setupFinalSummary");
  final.replaceChildren(
    summaryCard("Hjem", setupSummary.home_name || "Mangler"),
    summaryCard("Ejer", setupSummary.owner_name || "Mangler"),
    summaryCard("Tidszone", setupSummary.timezone || "Mangler"),
    summaryCard("Home Assistant", setupSummary.home_assistant.configured ? "Forbundet" : "Ikke forbundet"),
    summaryCard("Datakilder", `${setupSummary.selected_entity_count} valgt`),
  );
}

async function nextStep() {
  try {
    if (setupStep === 0) await saveHomeStep();
    if (setupStep === 1) {
      if (selectedHomeAssistantChoice() === "managed") {
        if (managedOnboardingState !== "connected") {
          showSetupNotice("Home Assistant skal være startet og forbundet med et gyldigt token, før du kan fortsætte.", "error");
          return;
        }
        showStep(2);
        return;
      }
      await runHomeAssistantAction(true);
    }
    if (setupStep === 2 && setupEntities.length) await saveEntitySettings();
    if (setupStep === 3) {
      await setupJson("/api/admin/setup/complete", { method: "POST" });
      showSetupNotice("Jarvis er sat op. Åbner administrationen…");
      window.setTimeout(() => window.location.assign("/admin"), 700);
      return;
    }
    showStep(setupStep + 1);
  } catch (error) {
    showSetupNotice(error.message, "error");
  }
}

async function initializeSetup() {
  ensureEntityPickerUi();
  try {
    const user = await setupJson("/api/auth/me");
    setupCsrfToken = user.csrf_token;
    const [home, ha, settings, managedPlan] = await Promise.all([
      setupJson("/api/admin/setup/home"),
      setupJson("/api/admin/setup/home-assistant"),
      setupJson("/api/admin/setup/home-assistant/entity-settings"),
      setupJson("/api/admin/setup/home-assistant/managed"),
    ]);
    document.getElementById("setupHomeName").value = home.home_name || "";
    document.getElementById("setupOwnerName").value = home.owner_name || user.display_name || "";
    document.getElementById("setupTimezone").value = home.timezone || "Europe/Copenhagen";
    document.getElementById("setupHaUrl").value = ha.home_assistant_url || "";
    document.getElementById("setupHaStatus").textContent = ha.configured ? "En gemt forbindelse blev fundet." : "Ikke konfigureret endnu.";
    document.getElementById("setupHaTokenStatus").textContent = ha.token_configured ? "Et token er allerede gemt. Feltet er med vilje tomt." : "Intet token er gemt.";
    if (managedPlan.requested && !ha.configured) document.getElementById("setupHaManagedChoice").checked = true;
    renderManagedInstallPlan(managedPlan);
    showHomeAssistantChoice();
    applyEntitySettings(settings);
  } catch (error) {
    showSetupNotice(`Opsætningen kunne ikke indlæses: ${error.message}`, "error");
  }
}

document.querySelectorAll("[data-step-button]").forEach((button) => button.addEventListener("click", () => showStep(Number(button.dataset.stepButton))));
document.getElementById("setupBackButton").addEventListener("click", () => showStep(setupStep - 1));
document.getElementById("setupNextButton").addEventListener("click", nextStep);
document.getElementById("setupManagedConfirmCheck").addEventListener("change", (event) => {
  document.getElementById("setupManagedInstallButton").disabled = !event.target.checked;
});
document.getElementById("setupManagedInstallButton").addEventListener("click", requestManagedInstallation);
document.getElementById("setupManagedTestTokenButton").addEventListener("click", async () => {
  try { await runManagedTokenAction(false); } catch (_error) { /* Status is shown by the action. */ }
});
document.getElementById("setupManagedSaveTokenButton").addEventListener("click", async () => {
  try { await runManagedTokenAction(true); } catch (_error) { /* Status is shown by the action. */ }
});
document.getElementById("setupTestHaButton").addEventListener("click", async () => {
  try { await runHomeAssistantAction(false); } catch (_error) { /* Status is shown by the action. */ }
});
document.getElementById("setupSaveHaButton").addEventListener("click", async () => {
  try {
    await runHomeAssistantAction(true);
    if (setupStep === 1) showStep(2);
  } catch (_error) { /* Status is shown by the action. */ }
});
document.getElementById("setupHaExistingChoice").addEventListener("change", showHomeAssistantChoice);
document.getElementById("setupHaManagedChoice").addEventListener("change", showHomeAssistantChoice);
document.getElementById("setupManagedPlanButton").addEventListener("click", requestManagedInstallPlan);
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stopManagedOnboardingPolling();
  else if (selectedHomeAssistantChoice() === "managed" && MANAGED_TRANSITIONAL_STATES.has(managedOnboardingState)) {
    refreshManagedOnboardingStatus();
  }
});

initializeSetup();
