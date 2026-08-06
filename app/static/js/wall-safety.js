const wallSafetyItems = {
  internet: document.querySelector('[data-wall-safety-item="internet"]'),
  doors: document.querySelector('[data-wall-safety-item="doors"]'),
  motion: document.querySelector('[data-wall-safety-item="motion"]'),
  cameras: document.querySelector('[data-wall-safety-item="cameras"]'),
  temperature: document.querySelector('[data-wall-safety-item="temperature"]'),
  humidity: document.querySelector('[data-wall-safety-item="humidity"]'),
  electricity_price: document.querySelector('[data-wall-safety-item="electricity-price"]'),
};
let wallSafetyRefreshInFlight = false;
let wallIdleTimer = null;
let wallLastMotionAt = Date.now();
const WALL_IDLE_TIMEOUT_MS = 2 * 60 * 1000;

function safetyStatusClass(value) {
  return ["ok", "warning", "critical", "unknown"].includes(value) ? value : "unknown";
}

function isWallDashboard() {
  return document.body.dataset.wallDashboard === "true";
}

function ensureWallIdleOverlay() {
  if (!isWallDashboard()) return null;
  let overlay = document.getElementById("wallIdleOverlay");
  if (overlay) return overlay;

  overlay = document.createElement("button");
  overlay.type = "button";
  overlay.id = "wallIdleOverlay";
  overlay.className = "wall-idle-overlay";
  overlay.setAttribute("aria-label", "Væk Jarvis vægskærm");
  overlay.hidden = true;

  const title = document.createElement("span");
  title.className = "wall-idle-text";
  title.textContent = "Jarvis sover";

  const hint = document.createElement("span");
  hint.className = "wall-idle-hint";
  hint.textContent = "Tryk eller bevæg dig for at vække skærmen";

  overlay.append(title, hint);
  overlay.addEventListener("click", () => markWallActivity());
  document.body.appendChild(overlay);
  return overlay;
}

function setWallIdle(active) {
  const overlay = ensureWallIdleOverlay();
  if (!overlay) return;
  overlay.hidden = !active;
  document.body.classList.toggle("wall-is-idle", active);
}

function scheduleWallIdleCheck() {
  if (!isWallDashboard()) return;
  if (wallIdleTimer) clearTimeout(wallIdleTimer);
  wallIdleTimer = setTimeout(() => {
    if (Date.now() - wallLastMotionAt >= WALL_IDLE_TIMEOUT_MS) {
      setWallIdle(true);
    } else {
      scheduleWallIdleCheck();
    }
  }, WALL_IDLE_TIMEOUT_MS);
}

function markWallActivity() {
  wallLastMotionAt = Date.now();
  setWallIdle(false);
  scheduleWallIdleCheck();
}

function updateWallIdleFromSafetyStatus(data) {
  if (!isWallDashboard() || !data || typeof data !== "object") return;
  const motion = data.motion || {};
  if (safetyStatusClass(motion.status) === "warning") {
    markWallActivity();
    return;
  }
  scheduleWallIdleCheck();
}

function wallSafetyIcon(key, status) {
  if (key === "internet") return status === "ok" ? "🌐" : "⚠️";
  if (key === "doors") return status === "ok" ? "🔒" : "🚪";
  if (key === "motion") return status === "warning" ? "👣" : "🟢";
  if (key === "cameras") return status === "ok" ? "📷" : "⚠️";
  if (key === "temperature") return "🌡️";
  if (key === "humidity") return "💧";
  if (key === "electricity_price") return "⚡";
  return "•";
}

function updateWallSafetyItem(key, data) {
  const item = wallSafetyItems[key];
  if (!item || !data) return;
  const status = safetyStatusClass(data.status);
  const icon = item.querySelector(".wall-safety-icon");
  const text = item.querySelector(".wall-safety-text");
  item.className = `wall-safety-item ${status}`;
  if (icon) icon.textContent = wallSafetyIcon(key, status);
  if (text) text.textContent = String(data.label || "Ukendt");
}

function renderWallSafetyStatus(data) {
  if (!data || typeof data !== "object") return;
  updateWallSafetyItem("internet", data.internet);
  updateWallSafetyItem("doors", data.doors);
  updateWallSafetyItem("motion", data.motion);
  updateWallSafetyItem("cameras", data.cameras);
  updateWallSafetyItem("temperature", data.temperature);
  updateWallSafetyItem("humidity", data.humidity);
  updateWallSafetyItem("electricity_price", data.electricity_price);
  updateWallIdleFromSafetyStatus(data);
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
      temperature: { status: "unknown", label: "Ukendt" },
      humidity: { status: "unknown", label: "Ukendt" },
      electricity_price: { status: "unknown", label: "Ukendt" },
    });
  } finally {
    wallSafetyRefreshInFlight = false;
  }
}

if (isWallDashboard()) {
  ["pointerdown", "keydown", "touchstart"].forEach((eventName) => {
    window.addEventListener(eventName, markWallActivity, { passive: true });
  });
  ensureWallIdleOverlay();
  scheduleWallIdleCheck();
}

if (typeof familyModuleEnabled !== "function" || familyModuleEnabled("safety")) {
  refreshWallSafetyStatus();
  setInterval(refreshWallSafetyStatus, 5000);
  window.addEventListener("focus", refreshWallSafetyStatus);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refreshWallSafetyStatus();
  });
}
