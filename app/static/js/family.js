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

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function percentage(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(0)} %` : "–";
}

function updateClock() {
  const now = new Date();
  const hour = now.getHours();
  setText("currentDate", dateFormatter.format(now));
  setText("currentTime", timeFormatter.format(now));
  setText("greeting", hour < 10 ? "Godmorgen" : hour < 18 ? "God eftermiddag" : "Godaften");
}

function renderStatus(health, mission) {
  const status = mission.overall_status || "unknown";
  const statusLabels = { ok: "Alt ser godt ud", warning: "Kræver opmærksomhed", critical: "Problem registreret" };
  const dot = document.getElementById("jarvisStatusDot");
  setText("jarvisStatus", statusLabels[status] || "Status ukendt");
  if (dot) dot.className = `status-dot ${status}`;

  setText("safeMode", mission.safe_mode ? "Til" : "Fra");
  setText("systemsOnline", `${mission.docker?.running ?? 0} af ${mission.docker?.total ?? 0}`);
  setText("incidentCount", String(mission.active_incidents?.length ?? 0));
  setText("criticalSystems", mission.critical_ok ? "Kører normalt" : "Kræver opmærksomhed");
  setText("currentTask", mission.what_jarvis_is_doing_now || "Afventer");
  setText("lastUpdated", timeFormatter.format(new Date()));
  setText("cpuMetric", percentage(health.cpu_percent));
  setText("memoryMetric", percentage(health.memory?.percent));
  setText("diskMetric", percentage(health.disk_root?.percent));
}

function renderUnavailable() {
  setText("jarvisStatus", "Kan ikke hente status");
  const dot = document.getElementById("jarvisStatusDot");
  if (dot) dot.className = "status-dot critical";
  setText("safeMode", "Ukendt");
  setText("systemsOnline", "Ukendt");
  setText("incidentCount", "Ukendt");
  setText("criticalSystems", "Status utilgængelig");
  setText("currentTask", "Status utilgængelig");
  setText("lastUpdated", timeFormatter.format(new Date()));
}

async function refreshFamilyDashboard() {
  try {
    const [healthResponse, missionResponse] = await Promise.all([
      fetch("/api/health"),
      fetch("/api/mission"),
    ]);
    if (!healthResponse.ok || !missionResponse.ok) throw new Error("Status kunne ikke hentes");
    const [health, mission] = await Promise.all([healthResponse.json(), missionResponse.json()]);
    renderStatus(health, mission);
  } catch (error) {
    renderUnavailable();
  }
}

updateClock();
refreshFamilyDashboard();
setInterval(updateClock, 1000);
setInterval(refreshFamilyDashboard, 30000);
