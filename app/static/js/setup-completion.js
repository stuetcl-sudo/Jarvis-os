function completionStatusCard(title, value, state, detail) {
  const card = document.createElement("section");
  card.className = `summary-card setup-check ${state}`;

  const icon = document.createElement("span");
  icon.className = "setup-check-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = state === "ok" ? "✓" : state === "optional" ? "–" : "!";

  const content = document.createElement("div");
  const heading = document.createElement("strong");
  heading.textContent = title;
  const status = document.createElement("span");
  status.textContent = value;
  const description = document.createElement("small");
  description.textContent = detail;
  content.append(heading, status, description);

  card.append(icon, content);
  return card;
}

function entityBreakdownText(summary) {
  const breakdown = summary.entity_breakdown || {};
  const parts = [];
  if (breakdown.calendars) parts.push(`${breakdown.calendars} kalender${breakdown.calendars === 1 ? "" : "e"}`);
  if (breakdown.task_lists) parts.push(`${breakdown.task_lists} liste${breakdown.task_lists === 1 ? "" : "r"}`);
  if (breakdown.climate_sensors) parts.push(`${breakdown.climate_sensors} klimasensor${breakdown.climate_sensors === 1 ? "" : "er"}`);
  if (breakdown.energy_sources) parts.push(`${breakdown.energy_sources} strømkilde${breakdown.energy_sources === 1 ? "" : "r"}`);
  if (breakdown.weather) parts.push("vejr");
  return parts.length ? parts.join(" · ") : "Ingen datakilder valgt endnu";
}

async function renderDetailedCompletionSummary() {
  try {
    const summary = await setupJson("/api/admin/setup/summary");
    setupSummary = summary;
    const final = document.getElementById("setupFinalSummary");
    if (!final) return;

    const homeReady = Boolean(summary.home_name && summary.owner_name && summary.timezone);
    const connected = Boolean(summary.home_assistant?.configured);
    const hasSources = Number(summary.selected_entity_count || 0) > 0;

    final.replaceChildren(
      completionStatusCard(
        "Hjemmet",
        homeReady ? `${summary.home_name} er klar` : "Oplysninger mangler",
        homeReady ? "ok" : "warning",
        homeReady ? `${summary.owner_name} · ${summary.timezone}` : "Gå tilbage til trin 1 og udfyld hjemmets oplysninger.",
      ),
      completionStatusCard(
        "Home Assistant",
        connected ? "Forbindelsen virker" : "Ikke forbundet",
        connected ? "ok" : "optional",
        connected ? "Adgangen er gemt lokalt og krypteret." : "Dette kan springes over og sættes op senere.",
      ),
      completionStatusCard(
        "Valgte funktioner",
        hasSources ? `${summary.selected_entity_count} datakilder valgt` : "Ingen valgt endnu",
        hasSources ? "ok" : "optional",
        entityBreakdownText(summary),
      ),
      completionStatusCard(
        "Klar til brug",
        summary.ready_to_complete ? "Jarvis kan startes" : "Opsætningen er ikke færdig",
        summary.ready_to_complete ? "ok" : "warning",
        summary.ready_to_complete ? "Tryk Afslut opsætning for at åbne administrationen." : "Ret de markerede punkter, før opsætningen afsluttes.",
      ),
    );

    const nextButton = document.getElementById("setupNextButton");
    if (nextButton && setupStep === 3) nextButton.disabled = !summary.ready_to_complete;
  } catch (error) {
    showSetupNotice(`Opsummeringen kunne ikke opdateres: ${error.message}`, "error");
  }
}

refreshWizardSummary = renderDetailedCompletionSummary;

document.querySelectorAll('[data-step-button="3"]').forEach((button) => {
  button.addEventListener("click", renderDetailedCompletionSummary);
});
