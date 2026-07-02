(() => {
  if (document.body.dataset.wallDashboard !== "true") return;
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
  });
})();
