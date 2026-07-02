function openSectionButton(section, label) {
  const button = element("button", "card-link", label);
  button.type = "button";
  button.addEventListener("click", () => showAdminSection(section));
  return button;
}

function renderMissionCards(data) {
  const waiting = actionRows.filter((action) => ["waiting_approval", "queued", "approved"].includes(action.status)).length;
  const critical = data.critical_services || [];
  const criticalRunning = critical.filter((service) => (service.docker_state || service.status) === "running").length;
  const cards = [
    {
      label: "Hjemmets status",
      value: labelStatus(data.overall_status),
      detail: data.overall_status === "ok" ? "Ingen kendte problemer" : "Se hvad der kræver opmærksomhed",
      tone: data.overall_status,
      section: "overview",
      link: "Se status",
    },
    {
      label: "Afventer dig",
      value: waiting === 0 ? "Intet" : String(waiting),
      detail: waiting === 0 ? "Ingen handlinger kræver godkendelse" : "Handlinger kræver din beslutning",
      tone: waiting ? "warning" : "ok",
      section: "advanced",
      link: "Se handlinger",
    },
    {
      label: "Vigtige tjenester",
      value: `${criticalRunning}/${critical.length}`,
      detail: criticalRunning === critical.length ? "Alle vigtige tjenester kører" : "En vigtig tjeneste er stoppet",
      tone: criticalRunning === critical.length ? "ok" : "critical",
      section: "home",
      link: "Se hjemmet",
    },
    {
      label: "Seneste kontrol",
      value: data.worker.running ? "Kører nu" : "Klar",
      detail: data.docker.docker_read_at ? `Status læst ${formatTimestamp(data.docker.docker_read_at)}` : "Status er netop opdateret",
      tone: "ok",
      section: "system",
      link: "Se systemstatus",
    },
  ].map((item) => {
    const card = element("article", `status-card ${safeClassToken(item.tone)}`);
    card.append(
      element("span", "status-label", item.label),
      element("strong", "", item.value),
      element("small", "", item.detail),
      openSectionButton(item.section, item.link),
    );
    return card;
  });
  replaceContent("missionCards", cards);
}

function formatTimestamp(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("da-DK", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  }).format(date);
}

function renderOverviewBanner(data) {
  const banner = document.getElementById("overviewBanner");
  banner.className = `overview-banner ${safeClassToken(data.overall_status)}`;
  const title = data.overall_status === "ok"
    ? "Hjemmets systemer ser normale ud"
    : data.overall_status === "critical"
      ? "Et vigtigt problem kræver opmærksomhed"
      : "Noget bør kontrolleres";
  const detail = data.overall_status === "ok"
    ? "Du behøver ikke gøre noget lige nu."
    : "Se listen nedenfor for at finde den vigtigste næste handling.";
  banner.replaceChildren(element("strong", "", title), element("span", "", detail));
}

function renderOverviewAttention(data, brain) {
  const items = [];
  const pending = actionRows.filter((action) => ["waiting_approval", "queued", "approved"].includes(action.status));
  if (data.active_incidents.length) {
    items.push({
      title: `${data.active_incidents.length} aktivt problem${data.active_incidents.length === 1 ? "" : "er"}`,
      detail: "Se systemstatus for at forstå konsekvensen.",
      section: "system",
      label: "Åbn systemstatus",
    });
  }
  if (pending.length) {
    items.push({
      title: `${pending.length} handling${pending.length === 1 ? "" : "er"} afventer dig`,
      detail: "Ingen handling udføres uden den eksisterende godkendelse og sikkerhedskontrol.",
      section: "advanced",
      label: "Se handlinger",
    });
  }
  if (data.unknown_containers.length) {
    items.push({
      title: `${data.unknown_containers.length} tjeneste${data.unknown_containers.length === 1 ? "" : "r"} er ikke vurderet`,
      detail: "Ikke-vurderede tjenester startes aldrig automatisk.",
      section: "advanced",
      label: "Vurder tjenester",
    });
  }
  if (!items.length && brain.recommendations.length) {
    items.push({
      title: "Der er en anbefaling til hjemmet",
      detail: brain.recommendations[0].title,
      section: "home",
      label: "Se anbefalinger",
    });
  }
  const nodes = items.slice(0, 4).map((item) => {
    const row = element("div", "attention-item");
    const text = document.createElement("div");
    text.append(element("strong", "", item.title), element("span", "", item.detail));
    const button = element("button", "secondary attention-action", item.label);
    button.type = "button";
    button.addEventListener("click", () => showAdminSection(item.section));
    row.append(text, button);
    return row;
  });
  replaceContent("overviewAttention", nodes.length ? nodes : [emptyState("Der er ikke noget, som kræver din opmærksomhed lige nu.")]);
}

function renderSystemHealth(health) {
  const metrics = [
    ["CPU", Number(health.cpu_percent || 0)],
    ["Hukommelse", Number(health.memory.percent || 0)],
    ["Swap", Number(health.swap.percent || 0)],
    ["Lagerplads", Number(health.disk_root.percent || 0)],
  ].map(([label, value]) => {
    const row = document.createElement("div");
    const progress = document.createElement("progress");
    progress.max = 100;
    progress.value = value;
    progress.setAttribute("aria-label", `${label}: ${pct(value)}`);
    row.append(element("span", "", label), progress, element("b", "", pct(value)));
    return row;
  });
  replaceContent("systemHealth", metrics);
}

function backgroundRefreshShouldPause() {
  const active = document.activeElement;
  return Boolean(active && active.closest("#section-advanced") && active.matches("input, select"));
}

async function refreshAll(options = {}) {
  const background = Boolean(options.background);
  if (refreshInFlight || (background && backgroundRefreshShouldPause())) return;
  refreshInFlight = true;
  try {
    const [data, brain, events, assets, policies, decisions, actions] = await Promise.all([
      getJson("/api/mission"),
      getJson("/api/brain"),
      getJson("/api/events/latest?limit=20"),
      getJson("/api/assets"),
      getJson("/api/policies"),
      getJson("/api/policy-decisions/latest?limit=20"),
      getJson("/api/actions?limit=25"),
    ]);

    containerRows = data.containers || [];
    assetRows = assets.assets || [];
    policyRows = policies.policies || [];
    decisionRows = decisions.decisions || [];
    actionRows = actions.actions || [];

    renderOverviewBanner(data);
    renderMissionCards(data);
    renderOverviewAttention(data, brain);
    renderActions();
    renderPolicies();
    renderModules();
    renderAssets();
    renderTechnicalAssets();

    document.getElementById("workerBadge").textContent = data.worker.running ? "Kører" : "Klar";
    document.getElementById("workerBadge").className = data.worker.running ? "pill working" : "pill";
    document.getElementById("workerText").textContent = data.what_jarvis_is_doing_now || "Ingen kontrol kører lige nu.";

    replaceContent(
      "eventFeed",
      events.events.length ? events.events.map(renderEvent) : [emptyState("Der er endnu ingen systemhændelser.")],
    );
    replaceContent(
      "unknownContainers",
      data.unknown_containers.length ? data.unknown_containers.map(renderUnknown) : [emptyState("Alle fundne tjenester er vurderet.")],
    );
    replaceContent(
      "observations",
      brain.observations.length ? brain.observations.slice(0, 6).map(renderObservation) : [emptyState("Der er ingen nye observationer.")],
    );
    replaceContent(
      "recommendations",
      brain.recommendations.length ? brain.recommendations.slice(0, 6).map(renderRecommendation) : [emptyState("Der er ingen aktive anbefalinger.")],
    );
    replaceContent(
      "criticalServices",
      data.critical_services.length ? data.critical_services.map(renderService) : [emptyState("Der er ingen tjenester markeret som vigtige.")],
    );
    renderSystemHealth(data.health);
    replaceContent("containers", containerRows.map(renderContainerRow));
    replaceContent(
      "stoppedByDesign",
      data.stopped_by_design.length ? data.stopped_by_design.map(renderService) : [emptyState("Ingen tjenester er markeret som bevidst stoppet.")],
    );
    replaceContent(
      "incidents",
      data.active_incidents.length ? data.active_incidents.map(renderObservation) : [emptyState("Der er ingen aktive problemer.")],
    );
    replaceContent("latestAction", [renderActionLog(data.latest_action)]);

    if (!background) showNotice("Status er opdateret.", "success");
  } catch (error) {
    showNotice(`Status kunne ikke opdateres. De senest viste oplysninger bevares. ${error.message}`, "error", 0);
  } finally {
    refreshInFlight = false;
  }
}

function showAdminSection(name, updateHash = true) {
  const sectionName = adminSections.includes(name) ? name : "overview";
  document.querySelectorAll("[data-admin-section]").forEach((section) => {
    section.hidden = section.dataset.adminSection !== sectionName;
  });
  document.querySelectorAll("[data-admin-target]").forEach((button) => {
    const selected = button.dataset.adminTarget === sectionName;
    button.setAttribute("aria-selected", selected ? "true" : "false");
    button.tabIndex = selected ? 0 : -1;
  });
  if (updateHash) history.replaceState(null, "", `#${sectionName}`);
  document.getElementById(`section-${sectionName}`)?.scrollIntoView({ block: "start" });
}

function bindNavigation() {
  const buttons = Array.from(document.querySelectorAll("[data-admin-target]"));
  buttons.forEach((button, index) => {
    button.addEventListener("click", () => showAdminSection(button.dataset.adminTarget));
    button.addEventListener("keydown", (event) => {
      if (!["ArrowDown", "ArrowUp", "ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let nextIndex = index;
      if (["ArrowDown", "ArrowRight"].includes(event.key)) nextIndex = (index + 1) % buttons.length;
      if (["ArrowUp", "ArrowLeft"].includes(event.key)) nextIndex = (index - 1 + buttons.length) % buttons.length;
      if (event.key === "Home") nextIndex = 0;
      if (event.key === "End") nextIndex = buttons.length - 1;
      buttons[nextIndex].focus();
      showAdminSection(buttons[nextIndex].dataset.adminTarget);
    });
  });
}

function bindControls() {
  document.getElementById("refreshButton").addEventListener("click", () => refreshAll());
  document.getElementById("runCheckButton").addEventListener("click", runOnce);
  document.getElementById("logoutButton").addEventListener("click", logout);
  document.getElementById("assetFilter").addEventListener("input", renderAssets);
}

async function initializeAdmin() {
  bindNavigation();
  bindControls();
  const initialSection = window.location.hash.replace("#", "");
  showAdminSection(initialSection, false);
  try {
    await loadAuth();
    await refreshAll({ background: true });
    window.setInterval(() => refreshAll({ background: true }), 15000);
  } catch (error) {
    showNotice(`Administrationen kunne ikke indlæses: ${error.message}`, "error", 0);
  }
}

initializeAdmin();
