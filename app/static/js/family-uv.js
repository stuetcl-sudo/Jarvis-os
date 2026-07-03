(() => {
  const badge = document.getElementById("weatherUv");
  const valueElement = document.getElementById("weatherUvValue");
  const labelElement = document.getElementById("weatherUvLabel");
  const UV_REFRESH_INTERVAL_MS = 120000;

  function uvCategory(rawValue) {
    const value = Number(rawValue);
    if (!Number.isFinite(value) || value < 0) return null;
    if (value <= 2) return { key: "green", label: "Solcreme ikke nødvendig" };
    if (value <= 5) return { key: "yellow", label: "Solcreme hvis du er længe ude" };
    if (value <= 7) return { key: "red", label: "Tag solcreme på" };
    return { key: "red", label: "Solcreme, skygge og pause" };
  }

  function hideUv() {
    if (badge) badge.hidden = true;
  }

  function preferredUvValue(weather) {
    const max = Number(weather?.uv_max_index);
    if (Number.isFinite(max) && max >= 0) return max;
    const current = Number(weather?.uv_index);
    return Number.isFinite(current) && current >= 0 ? current : null;
  }

  function renderUv(weather) {
    if (!badge || weather?.status === "not_configured" || weather?.status === "unavailable") {
      hideUv();
      return;
    }

    const value = preferredUvValue(weather);
    const category = uvCategory(value);
    if (!category) {
      hideUv();
      return;
    }

    const formatted = Number.isInteger(value) ? String(value) : value.toFixed(1);
    badge.className = `weather-uv weather-uv-${category.key}`;
    badge.setAttribute("aria-label", `UV i dag ${formatted}. ${category.label}`);
    if (valueElement) valueElement.textContent = `UV i dag ${formatted}`;
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
  setInterval(refreshUv, UV_REFRESH_INTERVAL_MS);
})();
