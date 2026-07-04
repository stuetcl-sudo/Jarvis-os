const wallSafetyItems = {
  internet: document.querySelector('[data-wall-safety-item="internet"]'),
  doors: document.querySelector('[data-wall-safety-item="doors"]'),
  motion: document.querySelector('[data-wall-safety-item="motion"]'),
  cameras: document.querySelector('[data-wall-safety-item="cameras"]'),
};
let wallSafetyRefreshInFlight = false;

function safetyStatusClass(value) {
  return ["ok", "warning", "critical", "unknown"].includes(value) ? value : "unknown";
}

function updateWallSafetyItem(key, data) {
  const item = wallSafetyItems[key];
  if (!item || !data) return;
  const status = safetyStatusClass(data.status);
  const text = item.querySelector(".wall-safety-text");
  item.className = `wall-safety-item ${status}`;
  if (text) text.textContent = String(data.label || "Ukendt");
}

function renderWallSafetyStatus(data) {
  if (!data || typeof data !== "object") return;
  updateWallSafetyItem("internet", data.internet);
  updateWallSafetyItem("doors", data.doors);
  updateWallSafetyItem("motion", data.motion);
  updateWallSafetyItem("cameras", data.cameras);
}

async function refreshWallSafetyStatus() {
  const strip = document.getElementById("wallSafetyStrip");
  if (!strip || document.body.dataset.wallDashboard !== "true" || wallSafetyRefreshInFlight) return;
  wallSafetyRefreshInFlight = true;
  try {
    const response = await fetch("/api/family/safety-status", { credentials: "same-origin" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderWallSafetyStatus(await response.json());
  } catch (error) {
    renderWallSafetyStatus({
      internet: { status: "unknown", label: "Ukendt" },
      doors: { status: "unknown", label: "Ukendt" },
      motion: { status: "unknown", label: "Ukendt" },
      cameras: { status: "unknown", label: "Ukendt" },
    });
  } finally {
    wallSafetyRefreshInFlight = false;
  }
}

refreshWallSafetyStatus();
setInterval(refreshWallSafetyStatus, 5000);
window.addEventListener("focus", refreshWallSafetyStatus);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshWallSafetyStatus();
});
