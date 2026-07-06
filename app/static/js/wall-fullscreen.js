(() => {
  const button = document.getElementById("wallFullscreen");
  if (!button) return;

  function fullscreenElement() {
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  function isFullscreen() {
    return Boolean(fullscreenElement());
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
  updateState();
})();
