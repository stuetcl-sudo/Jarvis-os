(() => {
  if (!familyModuleEnabled("weather")) return;
  const badge = document.getElementById("weatherUv");
  if (document.body.dataset.weatherUvEnabled === "false") {
    if (badge) badge.hidden = true;
    return;
  }
  const valueElement = document.getElementById("weatherUvValue");
  const labelElement = document.getElementById("weatherUvLabel");
  const UV_REFRESH_INTERVAL_MS = 120000;

  function uvCategory(rawValue) {
    const value = Number(rawValue);
    if (!Number.isFinite(value) || value < 0) return null;
    if (value <= 2) return { key: "green", label: "Lav UV" };
    if (value <= 5) return { key: "yellow", label: "Solcreme hvis du er længe ude" };
    if (value <= 7) return { key: "red", label: "Tag solcreme på" };
    return { key: "red", label: "Solcreme, skygge og pause" };
  }

  function hideUv() {
    if (badge) badge.hidden = true;
  }

  function preferredUvValue(weather) {
    const current = Number(weather?.uv_index);
    if (Number.isFinite(current) && current >= 0) return { value: current, label: "UV nu" };
    const max = Number(weather?.uv_max_index);
    return Number.isFinite(max) && max >= 0 ? { value: max, label: "UV max" } : null;
  }

  function renderUv(weather) {
    if (!badge || weather?.status === "not_configured" || weather?.status === "unavailable") {
      hideUv();
      return;
    }

    const uv = preferredUvValue(weather);
    const category = uvCategory(uv?.value);
    if (!uv || !category) {
      hideUv();
      return;
    }

    const formatted = Number.isInteger(uv.value) ? String(uv.value) : uv.value.toFixed(1);
    badge.className = `weather-uv weather-uv-${category.key}`;
    badge.setAttribute("aria-label", `${uv.label} ${formatted}. ${category.label}`);
    if (valueElement) valueElement.textContent = `${uv.label} ${formatted}`;
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
