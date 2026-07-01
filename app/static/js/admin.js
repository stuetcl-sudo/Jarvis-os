let containerRows = [];
let assetRows = [];
let policyRows = [];
let decisionRows = [];
let actionRows = [];
let csrfToken = "";

function element(tag, className = "", text = null) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== null) node.textContent = String(text);
  return node;
}

function replaceContent(target, children) {
  const node = typeof target === "string" ? document.getElementById(target) : target;
  if (!node) return;
  node.replaceChildren(...children);
}

function emptyState(message) {
  return element("p", "muted", message);
}

function safeClassToken(value, fallback = "unknown") {
  const token = String(value || "").toLowerCase();
  return /^[a-z0-9_-]+$/.test(token) ? token : fallback;
}

function statusNode(value) {
  const label = String(value || "unknown");
  return element("span", `status ${safeClassToken(label)}`, label);
}

async function getJson(url, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    options.headers = { ...(options.headers || {}), "X-CSRF-Token": csrfToken };
  }
  options.credentials = "same-origin";
  const response = await fetch(url, options);
  if (response.status === 401) {
    window.location.assign("/login?next=/admin");
    throw new Error("Session expired");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json();
}

async function loadAuth() {
  const user = await getJson("/api/auth/me");
  csrfToken = user.csrf_token;
  document.getElementById("authenticatedUser").textContent = user.display_name;
}

async function logout() {
  try {
    await getJson("/api/auth/logout", { method: "POST" });
  } finally {
    csrfToken = "";
    window.location.assign("/login");
  }
}

function pct(value) {
  return `${Number(value).toFixed(1)}%`;
}

function labelStatus(value) {
  if (value === "ok") return "OK";
  if (value === "warning") return "Warning";
  if (value === "critical") return "Critical";
  return value || "Unknown";
}

async function runOnce() {
  try {
    await getJson("/api/worker/run-once", { method: "POST" });
    await refreshAll();
  } catch (error) {
    alert(error.message);
    await refreshAll();
  }
}

async function queueRestart(assetId) {
  await getJson("/api/actions/queue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      asset_id: assetId,
      action_type: "docker.start_container",
      reason: "manual restart request from Mission Control",
      requires_approval: true,
    }),
  });
}

async function restartContainer(name) {
  const container = containerRows.find((item) => item.name === name);
  if (!container) return;
  try {
    await queueRestart(container.asset_id);
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

async function actionOp(id, operation) {
  try {
    await getJson(`/api/actions/${encodeURIComponent(id)}/${operation}`, { method: "POST" });
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

async function dismissRecommendation(id) {
  try {
    await getJson(`/api/recommendations/${id}/dismiss`, { method: "POST" });
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

async function togglePolicy(id, enable) {
  try {
    await getJson(`/api/policies/${encodeURIComponent(id)}/${enable ? "enable" : "disable"}`, {
      method: "POST",
    });
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

function recommendedClassification(container) {
  const name = String(container.name || "").toLowerCase();
  const image = String(container.image || "").toLowerCase();
  if (name.includes("test") || name.includes("demo") || name.includes("debug")) {
    return "stopped_by_design";
  }
  if (
    name.includes("proxy") || name.includes("gateway") || name.includes("dns") ||
    image.includes("proxy") || image.includes("gateway") || image.includes("dns")
  ) {
    return "critical";
  }
  return "optional";
}

function classificationControlId(control, index, scope = "table") {
  return `${control}-${scope}-${index}`;
}

async function classifyContainer(index, preset = null, scope = "table") {
  const container = containerRows[index];
  const classification = preset || document.getElementById(
    classificationControlId("cls", index, scope),
  ).value;
  const protectedBox = document.getElementById(classificationControlId("prot", index, scope));
  const autoBox = document.getElementById(classificationControlId("auto", index, scope));
  try {
    await getJson(`/api/service-classifications/${encodeURIComponent(container.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        classification,
        protected: protectedBox ? protectedBox.checked : false,
        auto_start_allowed: autoBox ? autoBox.checked : false,
      }),
    });
    await refreshAll();
  } catch (error) {
    alert(error.message);
  }
}

function classificationSelect(index, current, scope = "table") {
  const select = element("select");
  select.id = classificationControlId("cls", index, scope);
  [
    ["critical", "critical"],
    ["optional", "optional"],
    ["stopped_by_design", "stopped-by-design"],
    ["unknown", "unknown"],
  ].forEach(([value, label]) => {
    const option = element("option", "", label);
    option.value = value;
    option.selected = current === value;
    select.append(option);
  });
  return select;
}

function renderService(service) {
  const state = service.docker_state || service.status;
  const row = element("div", "service-row");
  row.append(element("b", "", service.name), statusNode(state));
  return row;
}

function renderActionLog(action) {
  if (!action) return emptyState("No legacy log entries yet.");
  const row = element("div", "logline");
  row.append(
    element("b", "", action.status),
    document.createTextNode(` ${action.action || ""} `),
    element("span", "", action.target || ""),
    element("small", "", action.created_at),
    element("em", "", action.reason || ""),
  );
  return row;
}

function renderObservation(item) {
  const card = element("div", `incident ${safeClassToken(item.severity)}`);
  card.append(
    element("b", "", item.title),
    element("span", "", item.service || item.category),
    element("p", "", item.detail),
  );
  return card;
}

function renderRecommendation(item) {
  const card = renderObservation(item);
  const button = element("button", "secondary", "Dismiss");
  button.type = "button";
  button.addEventListener("click", () => dismissRecommendation(item.id));
  card.append(button);
  return card;
}

function renderEvent(item) {
  const row = element("div", `event-row ${safeClassToken(item.severity)}`);
  row.append(
    element("b", "", item.type),
    element("span", "", `${item.source || ""} · ${item.asset_id || item.service || "system"}`),
    element("small", "", item.timestamp),
  );
  return row;
}

function renderContainerRow(container, index) {
  const state = container.docker_state || container.status;
  const canRequest = state === "exited" && !container.protected && container.classification === "optional";
  const row = document.createElement("tr");

  const nameCell = document.createElement("td");
  nameCell.textContent = container.name;

  const assetCell = document.createElement("td");
  const assetButton = element("button", "link-button", container.asset_id || "—");
  assetButton.type = "button";
  assetButton.addEventListener("click", () => showAsset(container.asset_id));
  assetCell.append(assetButton);

  const classificationCell = element("td", "", container.classification);
  const stateCell = document.createElement("td");
  stateCell.append(statusNode(state));
  const healthCell = element("td", "", container.health_status || "—");

  const protectedCell = document.createElement("td");
  const protectedBox = document.createElement("input");
  protectedBox.id = classificationControlId("prot", index);
  protectedBox.type = "checkbox";
  protectedBox.checked = Boolean(container.protected);
  protectedCell.append(protectedBox);

  const autoCell = document.createElement("td");
  const autoBox = document.createElement("input");
  autoBox.id = classificationControlId("auto", index);
  autoBox.type = "checkbox";
  autoBox.checked = Boolean(container.auto_start_allowed);
  autoCell.append(autoBox);

  const classifyCell = document.createElement("td");
  const saveButton = element("button", "secondary", "Save");
  saveButton.type = "button";
  saveButton.addEventListener("click", () => classifyContainer(index));
  classifyCell.append(classificationSelect(index, container.classification), " ", saveButton);

  const actionCell = document.createElement("td");
  if (canRequest) {
    const restartButton = element("button", "", "Request restart");
    restartButton.type = "button";
    restartButton.addEventListener("click", () => restartContainer(container.name));
    actionCell.append(restartButton);
  } else {
    actionCell.textContent = "—";
  }

  row.append(
    nameCell,
    assetCell,
    classificationCell,
    stateCell,
    healthCell,
    protectedCell,
    autoCell,
    classifyCell,
    actionCell,
  );
  return row;
}

function renderUnknown(container) {
  const index = containerRows.findIndex((item) => item.name === container.name);
  const state = container.docker_state || container.status;
  const recommendation = recommendedClassification(container);
  const card = element("article", "unknown-card");

  const top = element("div", "unknown-top");
  const identity = document.createElement("div");
  identity.append(
    element("b", "", container.name),
    element("small", "", container.image || "unknown image"),
  );
  top.append(identity, statusNode(state));

  const recommendationLine = element("div", "recommendation-line");
  recommendationLine.append("Recommendation: ", element("strong", "", recommendation));

  const quickButtons = element("div", "quick-buttons");
  [
    ["Critical", "critical"],
    ["Optional", "optional"],
    ["Stopped-by-design", "stopped_by_design"],
  ].forEach(([label, value]) => {
    const button = element("button", "", label);
    button.type = "button";
    button.addEventListener("click", () => classifyContainer(index, value, "unknown"));
    quickButtons.append(button);
  });

  const controls = element("div", "classification-controls");
  const typeLabel = element("label", "", "Type ");
  typeLabel.append(classificationSelect(index, container.classification, "unknown"));

  const protectedLabel = element("label", "", " Protected");
  const protectedBox = document.createElement("input");
  protectedBox.id = classificationControlId("prot", index, "unknown");
  protectedBox.type = "checkbox";
  protectedBox.checked = Boolean(container.protected);
  protectedLabel.prepend(protectedBox);

  const autoLabel = element("label", "", " Auto-start");
  const autoBox = document.createElement("input");
  autoBox.id = classificationControlId("auto", index, "unknown");
  autoBox.type = "checkbox";
  autoBox.checked = Boolean(container.auto_start_allowed);
  autoLabel.prepend(autoBox);

  const saveButton = element("button", "secondary", "Save");
  saveButton.type = "button";
  saveButton.addEventListener("click", () => classifyContainer(index, null, "unknown"));
  controls.append(typeLabel, protectedLabel, autoLabel, saveButton);

  card.append(
    top,
    recommendationLine,
    quickButtons,
    controls,
    emptyState("Unknown containers are never auto-started."),
  );
  return card;
}

function renderAssets() {
  const filter = String(document.getElementById("assetFilter")?.value || "").toLowerCase();
  const groups = {};
  assetRows
    .filter((asset) => !filter || JSON.stringify(asset).toLowerCase().includes(filter))
    .forEach((asset) => {
      groups[asset.plugin] = groups[asset.plugin] || [];
      groups[asset.plugin].push(asset);
    });

  const sections = Object.keys(groups).sort().map((plugin) => {
    const section = element("section", "asset-group");
    section.append(element("h3", "", plugin));
    groups[plugin].forEach((asset) => {
      const button = element("button", "asset-pill");
      button.type = "button";
      button.addEventListener("click", () => showAsset(asset.asset_id));
      button.append(
        element("b", "", asset.display_name),
        element("small", "", `${asset.asset_type || ""} · ${asset.state || ""}`),
      );
      section.append(button);
    });
    return section;
  });
  replaceContent("assetOverview", sections.length ? sections : [emptyState("No assets yet.")]);
}

async function showAsset(assetId) {
  if (!assetId) return;
  try {
    const data = await getJson(`/api/assets/${encodeURIComponent(assetId)}`);
    const asset = data.asset;
    const heading = element("h3", "", asset.display_name);
    const identity = document.createElement("p");
    identity.append(
      element("b", "", asset.asset_id),
      document.createTextNode(` · ${asset.asset_type || ""} · ${asset.plugin || ""}`),
    );
    const state = document.createElement("p");
    state.append(
      "State: ", element("b", "", asset.state),
      " Health: ", element("b", "", asset.health || "—"),
      " Classification: ", element("b", "", asset.classification),
    );
    const counts = element(
      "p",
      "",
      `Relationships: ${data.relationships.length} · Events: ${data.events.length} · Recommendations: ${data.recommendations.length}`,
    );
    replaceContent("assetDetail", [heading, identity, state, counts]);
  } catch (error) {
    alert(error.message);
  }
}

function renderPolicies() {
  const policies = policyRows.map((policy) => {
    const row = element("div", "policy-row");
    const details = document.createElement("div");
    details.append(
      element("b", "", policy.name),
      element("small", "", `${policy.policy_id || ""} · ${policy.trigger_event_type || ""} · priority ${policy.priority}`),
    );
    const button = element("button", "secondary", policy.enabled ? "Disable" : "Enable");
    button.type = "button";
    button.addEventListener("click", () => togglePolicy(policy.policy_id, !policy.enabled));
    row.append(details, button);
    return row;
  });
  replaceContent("policyList", policies.length ? policies : [emptyState("No policies.")]);

  const decisions = decisionRows.map((decision, index) => {
    const button = element("button", `decision-row ${decision.allowed ? "allowed" : "denied"}`);
    button.type = "button";
    button.addEventListener("click", () => showDecision(index));
    button.append(
      element("b", "", decision.action),
      element(
        "span",
        "",
        `${decision.policy_id || ""} · ${decision.matched ? "matched" : "not matched"} · ${decision.dry_run ? "dry-run" : "live"}`,
      ),
    );
    return button;
  });
  replaceContent("policyDecisions", decisions.length ? decisions : [emptyState("No decisions yet.")]);
}

function showDecision(index) {
  const decision = decisionRows[index];
  replaceContent("policyExplanation", [
    element("h3", "", `${decision.action || ""} ${decision.allowed ? "allowed" : "denied"}`),
    element(
      "p",
      "",
      `${decision.policy_id || ""} · asset ${decision.asset_id || "—"} · dry-run ${decision.dry_run ? "yes" : "no"}`,
    ),
    element("p", "", decision.explanation),
  ]);
}

function renderActions() {
  const actions = actionRows.map((action) => {
    const row = element("div", "policy-row");
    const details = document.createElement("div");
    details.append(
      element("b", "", action.action_type),
      element("small", "", `${action.status || ""} · ${action.asset_id || ""} · safety ${action.safety_status || ""}`),
      element("p", "muted", action.explanation || action.reason),
    );
    const buttons = element("div", "quick-buttons");
    ["approve", "run", "deny", "cancel"].forEach((operation) => {
      const button = element("button", "secondary", operation[0].toUpperCase() + operation.slice(1));
      button.type = "button";
      button.addEventListener("click", () => actionOp(action.action_id, operation));
      buttons.append(button);
    });
    row.append(details, buttons);
    return row;
  });
  replaceContent("actionQueue", actions.length ? actions : [emptyState("No queued actions.")]);
}

function renderMissionCards(data) {
  const cards = [
    ["Overall", labelStatus(data.overall_status), `card status-card ${safeClassToken(data.overall_status)}`],
    ["Safe mode", data.safe_mode ? "ON" : "OFF", "card"],
    ["Actions", actionRows.length, "card"],
    ["Docker live", `${data.docker.running}/${data.docker.total}`, "card", `${data.docker.stopped} exited`],
    ["Assets", assetRows.length, "card"],
  ].map(([label, value, className, detail]) => {
    const card = element("article", className);
    card.append(element("span", "", label), element("strong", "", value));
    if (detail) card.append(element("small", "", detail));
    return card;
  });
  replaceContent("missionCards", cards);
}

function renderSystemHealth(health) {
  const metrics = [
    ["CPU", pct(health.cpu_percent)],
    ["Memory", pct(health.memory.percent)],
    ["Swap", pct(health.swap.percent)],
    ["Disk /", pct(health.disk_root.percent)],
  ].map(([label, value]) => {
    const row = document.createElement("div");
    row.append(element("span", "", label), element("b", "", value));
    return row;
  });
  replaceContent("systemHealth", metrics);
}

async function refreshAll() {
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

  renderMissionCards(data);
  document.getElementById("workerBadge").textContent = data.worker.running ? "Working" : "Idle";
  document.getElementById("workerBadge").className = data.worker.running ? "pill working" : "pill";
  document.getElementById("workerText").textContent = data.what_jarvis_is_doing_now;
  renderActions();
  renderPolicies();
  renderAssets();

  replaceContent(
    "eventFeed",
    events.events.length ? events.events.map(renderEvent) : [emptyState("No events yet.")],
  );
  replaceContent(
    "unknownContainers",
    data.unknown_containers.length ? data.unknown_containers.map(renderUnknown) : [emptyState("No unknown containers.")],
  );
  replaceContent(
    "observations",
    brain.observations.length ? brain.observations.slice(0, 6).map(renderObservation) : [emptyState("No observations yet.")],
  );
  replaceContent(
    "recommendations",
    brain.recommendations.length ? brain.recommendations.slice(0, 6).map(renderRecommendation) : [emptyState("No active recommendations.")],
  );
  replaceContent(
    "criticalServices",
    data.critical_services.length ? data.critical_services.map(renderService) : [emptyState("No critical containers found.")],
  );
  renderSystemHealth(data.health);
  replaceContent("containers", containerRows.map(renderContainerRow));
  replaceContent(
    "stoppedByDesign",
    data.stopped_by_design.length ? data.stopped_by_design.map(renderService) : [emptyState("No stopped-by-design containers.")],
  );
  replaceContent(
    "incidents",
    data.active_incidents.length ? data.active_incidents.map(renderObservation) : [emptyState("No active incidents.")],
  );
  replaceContent("latestAction", [renderActionLog(data.latest_action)]);
}

async function initializeAdmin() {
  try {
    await loadAuth();
    await refreshAll();
    setInterval(refreshAll, 15000);
  } catch (error) {
    window.location.assign("/login?next=/admin");
  }
}

initializeAdmin();
