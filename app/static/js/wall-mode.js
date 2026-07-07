(() => {
  if (document.body.dataset.wallDashboard !== "true") return;

  function preferredProfile() {
    return {
      "wall-surface": "surface",
      "wall-ipad": "ipad",
      "wall-tablet": "tablet",
      "wall-square": "square",
      mobile: "mobile",
    }[document.body.dataset.wallPreferredProfile || ""] || "";
  }

  function profileFor(width, height) {
    const preferred = preferredProfile();
    if (preferred) return preferred;
    if (width <= 640) return "mobile";
    const ratio = height > 0 ? width / height : 1;
    if (ratio < 1.15 || width <= 920) return "square";
    if (width <= 1180) return "tablet";
    return "wide";
  }

  function applyScreenProfile() {
    const width = window.innerWidth || document.documentElement.clientWidth || 0;
    const height = window.innerHeight || document.documentElement.clientHeight || 0;
    document.body.dataset.wallScreenProfile = profileFor(width, height);
  }

  let profileTimer = null;
  function scheduleProfileUpdate() {
    window.clearTimeout(profileTimer);
    profileTimer = window.setTimeout(applyScreenProfile, 80);
  }

  applyScreenProfile();
  window.addEventListener("resize", scheduleProfileUpdate);
  window.addEventListener("orientationchange", scheduleProfileUpdate);

  const button = document.getElementById("wallFullscreen");
  if (!button) return;

  if (!document.documentElement.requestFullscreen || !document.exitFullscreen) {
    button.hidden = true;
    return;
  }

  button.addEventListener("click", async () => {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await document.documentElement.requestFullscreen();
    }
  });

  document.addEventListener("fullscreenchange", () => {
    button.textContent = document.fullscreenElement
      ? "Afslut fuld skærm"
      : "Fuld skærm";
    applyScreenProfile();
  });
})();
