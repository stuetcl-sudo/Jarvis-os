function ensureHomeAssistantPanel() {
  const section = document.querySelector('[data-admin-section="connections"]');
  if (!section || document.getElementById("homeAssistantSetupPanel")) return;

  const panel = element("section", "panel");
  panel.id = "homeAssistantSetupPanel";

  const heading = element("div", "panel-head");
  const headingText = element("div");
  headingText.append(
    element("h3", "", "Home Assistant"),
    element("p", "panel-help", "Forbind Jarvis til Home Assistant og hent kalendere, lister og sensorer automatisk."),
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
  urlInput.placeholder = "http://homeassistant.local:8123";
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

  form.append(urlLabel, tokenLabel, help, actions, result);
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
  ["testHomeAssistantButton", "discoverHomeAssistantButton", "saveHomeAssistantButton"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = busy;
  });
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
    const result = await getJson("/api/admin/setup/home-assistant/entities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(homeAssistantPayload()),
    });
    const counts = result.entities.reduce((acc, item) => {
      acc[item.domain] = (acc[item.domain] || 0) + 1;
      return acc;
    }, {});
    const summary = Object.entries(counts)
      .sort(([a], [b]) => a.localeCompare(b, "da"))
      .slice(0, 8)
      .map(([domain, count]) => `${domain}: ${count}`)
      .join(" · ");
    resultNode.textContent = `${result.count} entiteter fundet${summary ? ` — ${summary}` : ""}`;
    showNotice("Home Assistant-entiteterne er hentet.", "success");
  } catch (error) {
    resultNode.textContent = "Entiteterne kunne ikke hentes.";
    showNotice(`Entiteterne kunne ikke hentes: ${error.message}`, "error", 0);
  } finally {
    setHomeAssistantBusy(false);
  }
}

function initializeHomeAssistantSetup() {
  ensureHomeAssistantPanel();
  document.getElementById("testHomeAssistantButton").addEventListener("click", testHomeAssistantConnection);
  document.getElementById("discoverHomeAssistantButton").addEventListener("click", discoverHomeAssistantEntities);
  document.getElementById("homeAssistantSetupForm").addEventListener("submit", saveHomeAssistantConnection);
  loadHomeAssistantSummary();
}

initializeHomeAssistantSetup();
