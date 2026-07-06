(() => {
  const button = document.getElementById("wallFullscreen");
  if (!button) return;

  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
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

  function updateLabel() {
    button.textContent = fullscreenElement() ? "Luk fuld skærm" : "Fuld skærm";
  }

  button.addEventListener("click", async () => {
    try {
      if (fullscreenElement()) {
        await exitFullscreen();
      } else {
        await enterFullscreen();
      }
    } catch (error) {
      button.textContent = "Brug browserens fuld skærm";
    } finally {
      updateLabel();
    }
  });

  document.addEventListener("fullscreenchange", updateLabel);
  document.addEventListener("webkitfullscreenchange", updateLabel);
  updateLabel();
})();
