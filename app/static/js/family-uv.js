(() => {
  const badge = document.getElementById("weatherUv");
  const valueElement = document.getElementById("weatherUvValue");
  const labelElement = document.getElementById("weatherUvLabel");

  function uvCategory(rawValue) {
    const value = Number(rawValue);
    if (!Number.isFinite(value) || value < 0) return null;
    if (value <= 2) return { key: "green", label: "Lav" };
    if (value <= 5) return { key: "yellow", label: "Middel" };
    return { key: "red", label: "Høj" };
  }

  function hideUv() {
    if (badge) badge.hidden = true;
  }

  function renderUv(weather) {
    if (!badge || weather?.status === "not_configured" || weather?.status === "unavailable") {
      hideUv();
      return;
    }

    const category = uvCategory(weather?.uv_index);
    if (!category) {
      hideUv();
      return;
    }

    const value = Number(weather.uv_index);
    const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
    badge.className = `weather-uv weather-uv-${category.key}`;
    badge.setAttribute("aria-label", `UV-indeks ${formatted}, ${category.label.toLowerCase()}`);
    if (valueElement) valueElement.textContent = `UV ${formatted}`;
    if (labelElement) labelElement.textContent = category.label;
    badge.hidden = false;
  }

  async function refreshUv() {
    try {
      const response = await fetch("/api/family/weather", { credentials: "same-origin" });
      if (!response.ok) throw new Error("UV kunne ikke hentes");
      renderUv(await response.json());
    } catch (error) {
      hideUv();
    }
  }

  refreshUv();
  setInterval(refreshUv, 30000);
})();
