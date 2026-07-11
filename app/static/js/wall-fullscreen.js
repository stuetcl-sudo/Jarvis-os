(() => {
  if (document.body.dataset.wallDashboard !== "true") return;

  const profileMap = {
    "wall-large": "wide",
    "wall-surface": "surface",
    "wall-ipad": "ipad",
    "wall-tablet": "tablet",
    "wall-square": "square",
    mobile: "mobile",
  };

  function applyConfiguredProfile() {
    const preferred = document.body.dataset.wallPreferredProfile || "";
    const profile = profileMap[preferred] || "";
    if (profile) document.body.dataset.wallScreenProfile = profile;
  }

  applyConfiguredProfile();

  const button = document.getElementById("wallFullscreen");
  if (!button) return;

  const surfaceQuery = "(orientation: landscape) and (min-width: 1300px) and (max-width: 1400px) and (min-height: 880px) and (max-height: 940px) and (min-resolution: 1.75dppx) and (max-resolution: 2.25dppx)";

  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  function isFullscreen() {
    return Boolean(fullscreenElement());
  }

  function isViewportDebugEnabled() {
    const params = new URLSearchParams(window.location.search);
    return params.get("debug") === "viewport";
  }

  function ensureViewportDebugBadge() {
    if (!isViewportDebugEnabled()) return null;

    let badge = document.getElementById("wallViewportDebug");
    if (badge) return badge;

    badge = document.createElement("div");
    badge.id = "wallViewportDebug";
    badge.setAttribute("role", "status");
    badge.style.position = "fixed";
    badge.style.top = "8px";
    badge.style.left = "8px";
    badge.style.zIndex = "9999";
    badge.style.padding = "8px 11px";
    badge.style.borderRadius = "14px";
    badge.style.background = "#111111";
    badge.style.color = "#ffffff";
    badge.style.font = "700 13px system-ui, sans-serif";
    badge.style.lineHeight = "1.35";
    badge.style.boxShadow = "0 8px 22px rgba(0,0,0,.22)";
    document.body.appendChild(badge);
    return badge;
  }

  function updateViewportDebugBadge() {
    const badge = ensureViewportDebugBadge();
    if (!badge) return;

    const viewport = window.visualViewport;
    const viewportWidth = Math.round(viewport ? viewport.width : window.innerWidth);
    const viewportHeight = Math.round(viewport ? viewport.height : window.innerHeight);
    const cssWidth = window.innerWidth;
    const cssHeight = window.innerHeight;
    const ratio = window.devicePixelRatio || 1;
    const surfaceMatch = window.matchMedia(surfaceQuery).matches ? "ja" : "nej";
    const fullscreen = isFullscreen() ? "ja" : "nej";

    badge.textContent = `${cssWidth}×${cssHeight} CSS | visual ${viewportWidth}×${viewportHeight} | DPR ${ratio} | Surface ${surfaceMatch} | fullscreen ${fullscreen}`;
  }

  async function enterFullscreen() {
    const target = document.documentElement;
    const request = target.requestFullscreen || target.webkitRequestFullscreen;
    if (!request) return false;
    await request.call(target);
    return true;
  }

  async function exitFullscreen() {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (!exit) return false;
    await exit.call(document);
    return true;
  }

  function updateState() {
    const active = isFullscreen();
    document.body.classList.toggle("wall-is-fullscreen", active);
    button.textContent = active ? "Luk fuld skærm" : "Fuld skærm";
    updateViewportDebugBadge();
  }

  button.addEventListener("click", async () => {
    try {
      if (isFullscreen()) {
        await exitFullscreen();
      } else {
        await enterFullscreen();
      }
    } catch (error) {
      button.textContent = "Brug browserens fuld skærm";
    } finally {
      updateState();
    }
  });

  document.addEventListener("fullscreenchange", updateState);
  document.addEventListener("webkitfullscreenchange", updateState);
  window.addEventListener("resize", updateViewportDebugBadge);
  window.visualViewport?.addEventListener("resize", updateViewportDebugBadge);
  updateState();
})();
