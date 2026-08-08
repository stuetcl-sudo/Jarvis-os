let containerRows = [];
let assetRows = [];
let policyRows = [];
let decisionRows = [];
let actionRows = [];
let csrfToken = "";
let currentUser = null;
let refreshInFlight = false;
let noticeTimer = null;

const adminSections = [
  "overview",
  "home",
  "modules",
  "connections",
  "users",
  "system",
  "advanced",
];

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

function labelStatus(value) {
  if (value === "ok") return "Alt fungerer";
  if (value === "warning") return "Kræver opmærksomhed";
  if (value === "critical") return "Vigtigt problem";
  return value || "Ukendt";
}

function humanState(value) {
  const labels = {
    running: "Kører",
    exited: "Stoppet",
    dead: "Fejl",
    created: "Oprettet",
    paused: "Sat på pause",
    restarting: "Genstarter",
    healthy: "Sund",
    unhealthy: "Fejl",
    ok: "OK",
    warning: "Advarsel",
    critical: "Kritisk",
    error: "Fejl",
    failed: "Fejlet",
    completed: "Afsluttet",
    approved: "Godkendt",
    waiting_approval: "Afventer godkendelse",
    queued: "Afventer godkendelse",
    denied: "Afvist",
    cancelled: "Annulleret",
    unknown: "Ukendt",
  };
  return labels[String(value || "").toLowerCase()] || String(value || "Ukendt");
}

function statusNode(value) {
  const raw = String(value || "unknown");
  return element("span", `status ${safeClassToken(raw)}`, humanState(raw));
}

function pct(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

function showNotice(message, tone = "info", timeout = 5000) {
  const notice = document.getElementById("adminNotice");
  if (!notice) return;
  window.clearTimeout(noticeTimer);
  notice.textContent = String(message);
  notice.className = `admin-notice ${safeClassToken(tone, "info")}`;
  notice.hidden = false;
  if (timeout > 0) {
    noticeTimer = window.setTimeout(() => {
      notice.hidden = true;
    }, timeout);
  }
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
    throw new Error("Din session er udløbet");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText || "Anmodningen mislykkedes");
  }
  return response.json();
}

function roleLabel(role) {
  return {
    owner: "Ejer",
    adult: "Voksen",
    child: "Barn",
    wall_display: "Vægskærm",
  }[role] || role || "Ukendt";
}

function renderAccess(user) {
  document.getElementById("accessDisplayName").textContent = user.display_name || "—";
  document.getElementById("accessUsername").textContent = user.username || "—";
  document.getElementById("accessRole").textContent = roleLabel(user.role);
  document.getElementById("accessExplanation").textContent = user.role === "owner"
    ? "Som ejer kan du åbne administrationen og godkende handlinger, der kan påvirke hjemmets tjenester."
    : "Din rolle har begrænset adgang til administrationen.";
}

async function loadAuth() {
  const user = await getJson("/api/auth/me");
  csrfToken = user.csrf_token;
  currentUser = user;
  document.getElementById("authenticatedUser").textContent = `${user.display_name} · ${roleLabel(user.role)}`;
  renderAccess(user);
}

async function logout() {
  try {
    await getJson("/api/auth/logout", { method: "POST" });
  } finally {
    csrfToken = "";
    window.location.assign("/login");
  }
}

async function runOnce() {
  if (!window.confirm("Vil du køre en ekstra systemkontrol nu? Det ændrer ikke tjenester direkte.")) return;
  try {
    await getJson("/api/worker/run-once", { method: "POST" });
    showNotice("Systemkontrollen er kørt.", "success");
    await refreshAll();
  } catch (error) {
    showNotice(`Systemkontrollen kunne ikke køres: ${error.message}`, "error", 0);
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
  if (!window.confirm(`Opret en sikker genstartsanmodning for ${container.name}? Handlingen skal godkendes, før den kan køres.`)) return;
  try {
    await queueRestart(container.asset_id);
    showNotice("Genstartsanmodningen er oprettet og afventer godkendelse.", "success");
    await refreshAll();
  } catch (error) {
    showNotice(`Genstartsanmodningen kunne ikke oprettes: ${error.message}`, "error", 0);
  }
}

function operationLabel(operation) {
  return {
    approve: "Godkend",
    run: "Udfør",
    deny: "Afvis",
    cancel: "Annuller",
  }[operation] || operation;
}

function actionOperations(status) {
  if (["waiting_approval", "queued"].includes(status)) return ["approve", "deny", "cancel"];
  if (status === "approved") return ["run", "cancel"];
  return [];
}

async function actionOp(id, operation) {
  const label = operationLabel(operation);
  if (!window.confirm(`${label} denne handling?`)) return;
  try {
    await getJson(`/api/actions/${encodeURIComponent(id)}/${operation}`, { method: "POST" });
    showNotice(`Handlingen er opdateret: ${label.toLowerCase()}.`, "success");
    await refreshAll();
  } catch (error) {
    showNotice(`Handlingen kunne ikke opdateres: ${error.message}`, "error", 0);
  }
}

async function dismissRecommendation(id) {
  try {
    await getJson(`/api/recommendations/${id}/dismiss`, { method: "POST" });
    showNotice("Anbefalingen er skjult.", "success");
    await refreshAll();
  } catch (error) {
    showNotice(`Anbefalingen kunne ikke skjules: ${error.message}`, "error", 0);
  }
}

function classificationLabel(value) {
  return {
    critical: "Vigtig for hjemmet",
    optional: "Valgfri tjeneste",
    stopped_by_design: "Bevidst stoppet",
    unknown: "Ikke vurderet",
  }[value] || "Ikke vurderet";
}

function recommendedClassification(container) {
  const state = String(container.docker_state || container.status || "").toLowerCase();
  if (state === "exited") return "optional";
  return "unknown";
}

function classificationControlId(control, index, scope = "table") {
  return `${scope}-${control}-${index}`;
}

function classificationSelect(index, value, scope = "table") {
  const current = value || "unknown";
  const select = document.createElement("select");
  select.id = classificationControlId("cls", index, scope);
  [
    ["critical", "Vigtig for hjemmet"],
    ["optional", "Valgfri tjeneste"],
    ["stopped_by_design", "Bevidst stoppet"],
    ["unknown", "Ikke vurderet"],
  ].forEach(([value, label]) => {
    const option = element("option", "", label);
    option.value = value;
    option.selected = current === value;
    select.append(option);
  });
  return select;
}

async function classifyContainer(index, value = null, scope = "table") {
  const container = containerRows[index];
  if (!container) return;
  const select = document.getElementById(classificationControlId("cls", index, scope));
  const protectedBox = document.getElementById(classificationControlId("prot", index, scope));
  const autoBox = document.getElementById(classificationControlId("auto", index, scope));
  const classification = value || select?.value || container.classification || "unknown";
  const protectedValue = protectedBox ? protectedBox.checked : Boolean(container.protected);
  const autoStartValue = autoBox ? autoBox.checked : Boolean(container.auto_start_allowed);
  const confirmation = [
    `Gem vurderingen for ${container.name}?`,
    `Betydning: ${classificationLabel(classification)}.`,
    `Beskyttet: ${protectedValue ? "ja" : "nej"}.`,
    `Automatisk start: ${autoStartValue ? "tilladt" : "ikke tilladt"}.`,
  ].join("\n");
  if (!window.confirm(confirmation)) return;
  try {
    await getJson(`/api/service-classifications/${encodeURIComponent(container.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        classification,
        protected: protectedValue,
        auto_start_allowed: autoStartValue,
      }),
    });
    showNotice("Vurderingen er gemt.", "success");
    await refreshAll();
  } catch (error) {
    showNotice(`Vurderingen kunne ikke gemmes: ${error.message}`, "error", 0);
  }
}

async function togglePolicy(policyId, enabled) {
  const action = enabled ? "aktivere" : "deaktivere";
  const consequence = enabled
    ? "Reglen kan igen oprette automatiske forslag, når dens betingelser er opfyldt."
    : "Reglen stopper med at oprette nye automatiske forslag.";
  if (!window.confirm(`Vil du ${action} denne automatiske regel?\n${consequence}`)) return;
  try {
    await getJson(`/api/policies/${encodeURIComponent(policyId)}/${enabled ? "enable" : "disable"}`, { method: "POST" });
    showNotice(enabled ? "Reglen er aktiveret." : "Reglen er deaktiveret.", "success");
    await refreshAll();
  } catch (error) {
    showNotice(`Reglen kunne ikke ændres: ${error.message}`, "error", 0);
  }
}

function loadAdminScript(path) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = path;
    script.addEventListener("load", resolve, { once: true });
    script.addEventListener("error", () => reject(new Error(`Kunne ikke indlæse ${path}`)), { once: true });
    document.head.append(script);
  });
}

loadAdminScript("/static/js/admin-render.js")
  .then(() => loadAdminScript("/static/js/admin-page.js"))
  .then(() => loadAdminScript("/static/js/admin-connections.js"))
  .then(() => loadAdminScript("/static/js/admin-modules.js"))
  .then(() => loadAdminScript("/static/js/admin-safety-connections.js"))
  .then(() => loadAdminScript("/static/js/admin-screens.js"))
  .then(() => loadAdminScript("/static/js/admin-users.js"))
  .then(() => loadAdminScript("/static/js/admin-role-visibility.js"))
  .catch((error) => showNotice(`Administrationen kunne ikke startes: ${error.message}`, "error", 0));
