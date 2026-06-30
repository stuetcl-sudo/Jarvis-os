const dateFormatter = new Intl.DateTimeFormat("da-DK", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("da-DK", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

const supportedRoles = new Set(["anonymous", "owner", "adult", "child", "wall_display"]);
const pageRole = supportedRoles.has(document.body.dataset.familyRole)
  ? document.body.dataset.familyRole
  : "anonymous";
const personalRoles = new Set(["owner", "adult", "child"]);
const displayName = personalRoles.has(pageRole)
  ? (document.body.dataset.familyDisplayName || "").trim()
  : "";
const familyLabel = document.body.dataset.familyLabel || "Fælles overblik";
const familySubtitle = document.body.dataset.familySubtitle || "Her er et roligt overblik over hjemmet.";

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function percentage(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(0)} %` : "–";
}

function greetingFor(hour) {
  return hour < 10 ? "Godmorgen" : hour < 18 ? "God eftermiddag" : "Godaften";
}

function updateClock() {
  const now = new Date();
  const greeting = greetingFor(now.getHours());
  setText("currentDate", dateFormatter.format(now));
  setText("currentTime", timeFormatter.format(now));
  setText("greeting", displayName ? `${greeting}, ${displayName}` : greeting);
  setText("familyViewLabel", familyLabel);
  setText("familySubtitle", familySubtitle);
}

function calmStatus(status) {
  const labels = {
    ok: "Alt ser roligt ud",
    warning: "Noget kræver opmærksomhed",
    critical: "Der er registreret et problem",
  };
  return labels[status] || "Status er ukendt";
}

function renderMission(mission) {
  const status = mission.overall_status || "unknown";
  const dot = document.getElementById("jarvisStatusDot");
  setText("overallHomeStatus", calmStatus(status));
  setText("lastUpdated", timeFormatter.format(new Date()));
  setText("jarvisStatus", calmStatus(status));
  if (dot) dot.className = `status-dot ${status}`;
  setText("safeMode", mission.safe_mode ? "Til" : "Fra");
  setText("systemsOnline", `${mission.docker?.running ?? 0} af ${mission.docker?.total ?? 0}`);
  setText("incidentCount", String(mission.active_incidents?.length ?? 0));
}

function renderHealth(health) {
  setText("cpuMetric", percentage(health.cpu_percent));
  setText("memoryMetric", percentage(health.memory?.percent));
  setText("diskMetric", percentage(health.disk_root?.percent));
}

function renderUnavailable() {
  setText("overallHomeStatus", "Status er ikke tilgængelig");
  setText("lastUpdated", timeFormatter.format(new Date()));
  setText("jarvisStatus", "Kan ikke hente status");
  const dot = document.getElementById("jarvisStatusDot");
  if (dot) dot.className = "status-dot critical";
  setText("safeMode", "Ukendt");
  setText("systemsOnline", "Ukendt");
  setText("incidentCount", "Ukendt");
}

async function refreshFamilyDashboard() {
  try {
    const missionResponse = await fetch("/api/mission");
    if (!missionResponse.ok) throw new Error("Status kunne ikke hentes");
    const mission = await missionResponse.json();
    renderMission(mission);

    if (pageRole === "owner") {
      const healthResponse = await fetch("/api/health");
      if (!healthResponse.ok) throw new Error("Systemstatus kunne ikke hentes");
      renderHealth(await healthResponse.json());
    }
  } catch (error) {
    renderUnavailable();
  }
}

updateClock();
refreshFamilyDashboard();
setInterval(updateClock, 1000);
setInterval(refreshFamilyDashboard, 30000);
