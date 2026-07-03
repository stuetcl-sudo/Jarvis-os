let setupStep = 0;
let setupCsrfToken = "";
let setupSummary = null;

async function setupJson(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  options.credentials = "same-origin";
  if (method !== "GET" && method !== "HEAD") {
    options.headers = { ...(options.headers || {}), "X-CSRF-Token": setupCsrfToken };
  }
  const response = await fetch(url, options);
  if (response.status === 401) {
    window.location.assign(`/login?next=${encodeURIComponent("/setup")}`);
    throw new Error("Din session er udløbet");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText || "Anmodningen mislykkedes");
  }
  return response.json();
}

function showSetupNotice(message, tone = "success") {
  const notice = document.getElementById("setupNotice");
  notice.textContent = message;
  notice.className = `setup-notice ${tone}`;
  notice.hidden = false;
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
    ? "Forbindelsen er testet og gemt sikkert."
    : `Forbindelsen virker: ${result.message}`;
  if (save) document.getElementById("setupHaToken").value = "";
  return result;
}

function summaryCard(title, value) {
  const card = document.createElement("div");
  card.className = "summary-card";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const span = document.createElement("span");
  span.textContent = value;
  card.append(strong, span);
  return card;
}

async function refreshWizardSummary() {
  setupSummary = await setupJson("/api/admin/setup/summary");
  const content = document.getElementById("setupContentSummary");
  content.replaceChildren(
    summaryCard("Home Assistant", setupSummary.home_assistant.configured ? "Forbundet" : "Ikke forbundet"),
    summaryCard("Valgte datakilder", `${setupSummary.selected_entity_count} valgt`),
  );
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
    if (setupStep === 1 && document.getElementById("setupHaUrl").value.trim()) await testHomeAssistant(true);
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
  try {
    const user = await setupJson("/api/auth/me");
    setupCsrfToken = user.csrf_token;
    const [home, ha] = await Promise.all([
      setupJson("/api/admin/setup/home"),
      setupJson("/api/admin/setup/home-assistant"),
    ]);
    document.getElementById("setupHomeName").value = home.home_name || "";
    document.getElementById("setupOwnerName").value = home.owner_name || user.display_name || "";
    document.getElementById("setupTimezone").value = home.timezone || "Europe/Copenhagen";
    document.getElementById("setupHaUrl").value = ha.home_assistant_url || "";
    document.getElementById("setupHaStatus").textContent = ha.configured ? "En gemt forbindelse blev fundet." : "Ikke konfigureret endnu.";
  } catch (error) {
    showSetupNotice(`Opsætningen kunne ikke indlæses: ${error.message}`, "error");
  }
}

document.querySelectorAll("[data-step-button]").forEach((button) => {
  button.addEventListener("click", () => showStep(Number(button.dataset.stepButton)));
});
document.getElementById("setupBackButton").addEventListener("click", () => showStep(setupStep - 1));
document.getElementById("setupNextButton").addEventListener("click", nextStep);
document.getElementById("setupTestHaButton").addEventListener("click", async () => {
  try {
    await testHomeAssistant(false);
    showSetupNotice("Home Assistant-forbindelsen virker.");
  } catch (error) {
    showSetupNotice(error.message, "error");
  }
});
document.getElementById("setupSaveHaButton").addEventListener("click", async () => {
  try {
    await testHomeAssistant(true);
    showSetupNotice("Home Assistant-forbindelsen er gemt sikkert.");
  } catch (error) {
    showSetupNotice(error.message, "error");
  }
});

initializeSetup();
