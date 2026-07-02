function renderService(service) {
  const state = service.docker_state || service.status;
  const row = element("div", "service-row");
  const details = document.createElement("div");
  details.append(element("b", "", service.name));
  if (service.image) details.append(element("small", "muted", service.image));
  row.append(details, statusNode(state));
  return row;
}

function renderActionLog(action) {
  if (!action) return emptyState("Der er endnu ingen tekniske logposter.");
  const row = element("div", "logline");
  row.append(
    element("b", "", humanState(action.status)),
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
  const button = element("button", "secondary", "Skjul anbefaling");
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

function appendTableCell(row, label, child) {
  const cell = document.createElement("td");
  cell.dataset.label = label;
  if (child instanceof Node) cell.append(child);
  else cell.textContent = String(child ?? "—");
  row.append(cell);
  return cell;
}

function checkboxControl(id, checked, ariaLabel) {
  const label = element("label", "checkbox-control");
  const input = document.createElement("input");
  input.id = id;
  input.type = "checkbox";
  input.checked = Boolean(checked);
  input.setAttribute("aria-label", ariaLabel);
  label.append(input, element("span", "visually-hidden", ariaLabel));
  return label;
}

function renderContainerRow(container, index) {
  const state = container.docker_state || container.status;
  const canRequest = state === "exited" && !container.protected && container.classification === "optional";
  const row = document.createElement("tr");

  appendTableCell(row, "Navn", container.name);

  const assetButton = element("button", "link-button", container.asset_id || "—");
  assetButton.type = "button";
  assetButton.addEventListener("click", () => {
    showAdminSection("connections");
    showAsset(container.asset_id);
  });
  appendTableCell(row, "Teknisk ID", assetButton);

  appendTableCell(row, "Betydning", classificationLabel(container.classification));
  appendTableCell(row, "Status", statusNode(state));
  appendTableCell(row, "Sundhed", container.health_status || "—");

  appendTableCell(
    row,
    "Beskyttet",
    checkboxControl(
      classificationControlId("prot", index),
      container.protected,
      `Beskyt ${container.name} mod automatiske ændringer`,
    ),
  );
  appendTableCell(
    row,
    "Automatisk start",
    checkboxControl(
      classificationControlId("auto", index),
      container.auto_start_allowed,
      `Tillad automatisk start af ${container.name}`,
    ),
  );

  const classificationWrap = element("div", "classification-controls");
  const saveButton = element("button", "secondary", "Gem");
  saveButton.type = "button";
  saveButton.addEventListener("click", () => classifyContainer(index));
  classificationWrap.append(classificationSelect(index, container.classification), saveButton);
  appendTableCell(row, "Gem vurdering", classificationWrap);

  if (canRequest) {
    const restartButton = element("button", "", "Anmod om genstart");
    restartButton.type = "button";
    restartButton.addEventListener("click", () => restartContainer(container.name));
    appendTableCell(row, "Handling", restartButton);
  } else {
    appendTableCell(row, "Handling", "—");
  }
  return row;
}

function setClassificationPreset(index, value, scope) {
  const select = document.getElementById(classificationControlId("cls", index, scope));
  if (select) {
    select.value = value;
    select.focus();
    showNotice("Valget er ændret. Tryk på “Gem vurdering” for at gemme det.", "warning");
  }
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
    element("small", "", container.image || "Ukendt image"),
  );
  top.append(identity, statusNode(state));

  const recommendationLine = element("div", "recommendation-line");
  recommendationLine.append("Forslag: ", element("strong", "", classificationLabel(recommendation)));

  const quickButtons = element("div", "quick-buttons");
  [
    ["Vigtig for hjemmet", "critical"],
    ["Valgfri tjeneste", "optional"],
    ["Bevidst stoppet", "stopped_by_design"],
  ].forEach(([label, value]) => {
    const button = element("button", "secondary", label);
    button.type = "button";
    button.addEventListener("click", () => setClassificationPreset(index, value, "unknown"));
    quickButtons.append(button);
  });

  const controls = element("div", "classification-controls");
  const typeLabel = element("label", "", "Betydning for hjemmet");
  typeLabel.append(classificationSelect(index, container.classification, "unknown"));

  const protectedLabel = element("label", "checkbox-control", "Beskyttet");
  const protectedBox = document.createElement("input");
  protectedBox.id = classificationControlId("prot", index, "unknown");
  protectedBox.type = "checkbox";
  protectedBox.checked = Boolean(container.protected);
  protectedLabel.prepend(protectedBox);

  const autoLabel = element("label", "checkbox-control", "Tillad automatisk start");
  const autoBox = document.createElement("input");
  autoBox.id = classificationControlId("auto", index, "unknown");
  autoBox.type = "checkbox";
  autoBox.checked = Boolean(container.auto_start_allowed);
  autoLabel.prepend(autoBox);

  const saveButton = element("button", "", "Gem vurdering");
  saveButton.type = "button";
  saveButton.addEventListener("click", () => classifyContainer(index, null, "unknown"));
  controls.append(typeLabel, protectedLabel, autoLabel, saveButton);

  card.append(
    top,
    recommendationLine,
    quickButtons,
    controls,
    emptyState("Ikke-genkendte tjenester startes aldrig automatisk."),
  );
  return card;
}

function friendlyPluginName(plugin) {
  const normalized = String(plugin || "unknown").toLowerCase();
  const labels = {
    core: "Jarvis OS",
    docker: "Serverens tjenester",
    system: "System",
    home_assistant: "Home Assistant",
    calendar: "Kalender",
    weather: "Vejr",
    routines: "Rutiner",
  };
  return labels[normalized] || String(plugin || "Andre funktioner").replaceAll("_", " ");
}

function renderModules() {
  const groups = {};
  assetRows.forEach((asset) => {
    const key = asset.plugin || "unknown";
    groups[key] = groups[key] || [];
    groups[key].push(asset);
  });
  const cards = Object.keys(groups).sort().map((plugin) => {
    const items = groups[plugin];
    const healthy = items.filter((asset) => !["error", "failed", "dead", "exited"].includes(String(asset.state || asset.health || "").toLowerCase())).length;
    const card = element("article", "module-card");
    card.append(
      element("strong", "", friendlyPluginName(plugin)),
      element("span", "", `${healthy}/${items.length}`),
      element("small", "", healthy === items.length ? "Tilgængelig" : "Nogle dele kræver opmærksomhed"),
    );
    return card;
  });
  replaceContent("moduleOverview", cards.length ? cards : [emptyState("Der er endnu ingen registrerede funktioner.")]);
}

function renderAssets() {
  const filter = String(document.getElementById("assetFilter")?.value || "").toLowerCase();
  const groups = {};
  assetRows
    .filter((asset) => !filter || JSON.stringify(asset).toLowerCase().includes(filter))
    .forEach((asset) => {
      const key = asset.plugin || "unknown";
      groups[key] = groups[key] || [];
      groups[key].push(asset);
    });

  const sections = Object.keys(groups).sort().map((plugin) => {
    const section = element("section", "asset-group");
    section.append(element("h3", "", friendlyPluginName(plugin)));
    groups[plugin].forEach((asset) => {
      const button = element("button", "asset-pill");
      button.type = "button";
      button.addEventListener("click", () => showAsset(asset.asset_id));
      button.append(
        element("b", "", asset.display_name),
        element("small", "", `${humanState(asset.state)} · ${asset.health ? humanState(asset.health) : "Status registreret"}`),
      );
      section.append(button);
    });
    return section;
  });
  replaceContent("assetOverview", sections.length ? sections : [emptyState("Ingen forbindelser matcher søgningen.")]);
}

function renderTechnicalAssets() {
  const groups = {};
  assetRows.forEach((asset) => {
    const key = asset.plugin || "unknown";
    groups[key] = groups[key] || [];
    groups[key].push(asset);
  });
  const sections = Object.keys(groups).sort().map((plugin) => {
    const section = element("section", "asset-group");
    section.append(element("h3", "", plugin));
    groups[plugin].forEach((asset) => {
      const row = element("div", "asset-pill");
      row.append(
        element("b", "", asset.display_name),
        element("small", "", `${asset.asset_id || "—"} · ${asset.asset_type || "—"} · ${asset.state || "—"}`),
      );
      section.append(row);
    });
    return section;
  });
  replaceContent("assetTechnicalOverview", sections.length ? sections : [emptyState("Der er endnu ingen tekniske assets.")]);
}

async function showAsset(assetId) {
  if (!assetId) return;
  try {
    const data = await getJson(`/api/assets/${encodeURIComponent(assetId)}`);
    const asset = data.asset;
    const heading = element("h3", "", asset.display_name);
    const state = document.createElement("p");
    state.append(
      "Status: ", element("b", "", humanState(asset.state)),
      " · Sundhed: ", element("b", "", asset.health ? humanState(asset.health) : "Ikke oplyst"),
    );
    const counts = element(
      "p",
      "",
      `Forbindelser: ${data.relationships.length} · Hændelser: ${data.events.length} · Anbefalinger: ${data.recommendations.length}`,
    );
    const technical = element("details", "technical-detail");
    technical.append(
      element("summary", "", "Vis tekniske detaljer"),
      element("p", "", `Teknisk ID: ${asset.asset_id}`),
      element("p", "", `Type: ${asset.asset_type || "—"} · Kilde: ${asset.plugin || "—"} · Klassifikation: ${asset.classification || "—"}`),
    );
    replaceContent("assetDetail", [heading, state, counts, technical]);
  } catch (error) {
    showNotice(`Forbindelsen kunne ikke indlæses: ${error.message}`, "error", 0);
  }
}

function renderPolicies() {
  const policies = policyRows.map((policy) => {
    const row = element("div", "policy-row");
    const details = document.createElement("div");
    details.append(
      element("b", "", policy.name),
      element("small", "", `${policy.policy_id || ""} · ${policy.trigger_event_type || ""} · prioritet ${policy.priority}`),
    );
    const button = element("button", policy.enabled ? "danger" : "secondary", policy.enabled ? "Deaktivér" : "Aktivér");
    button.type = "button";
    button.addEventListener("click", () => togglePolicy(policy.policy_id, !policy.enabled));
    row.append(details, button);
    return row;
  });
  replaceContent("policyList", policies.length ? policies : [emptyState("Der er ingen automatiske regler.")]);

  const decisions = decisionRows.map((decision, index) => {
    const button = element("button", `decision-row ${decision.allowed ? "allowed" : "denied"}`);
    button.type = "button";
    button.addEventListener("click", () => showDecision(index));
    button.append(
      element("b", "", decision.action),
      element(
        "span",
        "",
        `${decision.policy_id || ""} · ${decision.matched ? "regel matchede" : "regel matchede ikke"} · ${decision.dry_run ? "testtilstand" : "aktiv tilstand"}`,
      ),
    );
    return button;
  });
  replaceContent("policyDecisions", decisions.length ? decisions : [emptyState("Der er endnu ingen beslutninger.")]);
}

function showDecision(index) {
  const decision = decisionRows[index];
  replaceContent("policyExplanation", [
    element("h3", "", `${decision.action || ""} · ${decision.allowed ? "tilladt" : "afvist"}`),
    element(
      "p",
      "",
      `${decision.policy_id || ""} · asset ${decision.asset_id || "—"} · testtilstand ${decision.dry_run ? "ja" : "nej"}`,
    ),
    element("p", "", decision.explanation),
  ]);
}

function friendlyActionType(actionType) {
  return {
    "docker.start_container": "Start tjeneste igen",
    "recommendation.create": "Opret anbefaling",
  }[actionType] || actionType || "Ukendt handling";
}

function renderActions() {
  const actions = actionRows.map((action) => {
    const row = element("div", "policy-row");
    const details = document.createElement("div");
    details.append(
      element("b", "", friendlyActionType(action.action_type)),
      element("small", "", `${humanState(action.status)} · ${action.asset_id || ""} · sikkerhed ${action.safety_status || "ikke kontrolleret"}`),
      element("p", "muted", action.explanation || action.reason),
    );
    const buttons = element("div", "quick-buttons");
    actionOperations(action.status).forEach((operation) => {
      const button = element("button", operation === "deny" ? "danger" : "secondary", operationLabel(operation));
      button.type = "button";
      button.addEventListener("click", () => actionOp(action.action_id, operation));
      buttons.append(button);
    });
    if (!buttons.childElementCount) {
      buttons.append(statusNode(action.status));
    }
    row.append(details, buttons);
    return row;
  });
  replaceContent("actionQueue", actions.length ? actions : [emptyState("Der er ingen handlinger i køen.")]);
}
