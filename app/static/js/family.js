const dateFormatter = new Intl.DateTimeFormat("da-DK", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});
const timeFormatter = new Intl.DateTimeFormat("da-DK", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const weekdayFormatter = new Intl.DateTimeFormat("da-DK", {
  weekday: "short",
});

const supportedRoles = new Set(["anonymous", "owner", "adult", "child", "wall_display"]);
const pageRole = supportedRoles.has(document.body.dataset.familyRole)
  ? document.body.dataset.familyRole
  : "anonymous";
const personalRoles = new Set(["owner", "adult", "child"]);
const displayName = personalRoles.has(pageRole)
  ? (document.body.dataset.familyDisplayName || "").trim()
  : "";
const familyLabel = document.body.dataset.familyLabel || "Fælles overblik";
const familySubtitle = document.body.dataset.familySubtitle || "Her er et roligt overblik over hjemmet.";

const weatherConditions = {
  "clear-night": { label: "Klart", symbol: "🌙" },
  cloudy: { label: "Skyet", symbol: "☁️" },
  fog: { label: "Tåge", symbol: "🌫️" },
  hail: { label: "Hagl", symbol: "🌨️" },
  lightning: { label: "Torden", symbol: "⚡" },
  "lightning-rainy": { label: "Tordenbyger", symbol: "⛈️" },
  partlycloudy: { label: "Delvist skyet", symbol: "⛅" },
  pouring: { label: "Kraftig regn", symbol: "🌧️" },
  rainy: { label: "Regn", symbol: "🌧️" },
  snowy: { label: "Sne", symbol: "❄️" },
  "snowy-rainy": { label: "Slud", symbol: "🌨️" },
  sunny: { label: "Solrigt", symbol: "☀️" },
  windy: { label: "Blæsende", symbol: "💨" },
  "windy-variant": { label: "Blæsende og skyet", symbol: "🌬️" },
  exceptional: { label: "Usædvanligt vejr", symbol: "🌡️" },
};

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = value;
}

function percentage(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${number.toFixed(0)} %` : "–";
}

function measurement(value, unit = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "–";
  const digits = Number.isInteger(number) ? 0 : 1;
  return `${number.toFixed(digits)}${unit ? ` ${unit}` : ""}`;
}

function greetingFor(hour) {
  return hour < 10 ? "Godmorgen" : hour < 18 ? "God eftermiddag" : "Godaften";
}

function updateClock() {
  const now = new Date();
  const greeting = greetingFor(now.getHours());
  setText("currentDate", dateFormatter.format(now));
  setText("currentTime", timeFormatter.format(now));
  setText("greeting", displayName ? `${greeting}, ${displayName}` : greeting);
  setText("familyViewLabel", familyLabel);
  setText("familySubtitle", familySubtitle);
}

function calmStatus(status) {
  const labels = {
    ok: "Alt ser roligt ud",
    warning: "Noget kræver opmærksomhed",
    critical: "Der er registreret et problem",
  };
  return labels[status] || "Status er ukendt";
}

function renderMission(mission) {
  const status = mission.overall_status || "unknown";
  const dot = document.getElementById("jarvisStatusDot");
  setText("overallHomeStatus", calmStatus(status));
  setText("lastUpdated", timeFormatter.format(new Date()));
  setText("jarvisStatus", calmStatus(status));
  if (dot) dot.className = `status-dot ${status}`;
  setText("safeMode", mission.safe_mode ? "Til" : "Fra");
  setText("systemsOnline", `${mission.docker?.running ?? 0} af ${mission.docker?.total ?? 0}`);
  setText("incidentCount", String(mission.active_incidents?.length ?? 0));
}

function renderHealth(health) {
  setText("cpuMetric", percentage(health.cpu_percent));
  setText("memoryMetric", percentage(health.memory?.percent));
  setText("diskMetric", percentage(health.disk_root?.percent));
}

function renderUnavailable() {
  setText("overallHomeStatus", "Status er ikke tilgængelig");
  setText("lastUpdated", timeFormatter.format(new Date()));
  setText("jarvisStatus", "Kan ikke hente status");
  const dot = document.getElementById("jarvisStatusDot");
  if (dot) dot.className = "status-dot critical";
  setText("safeMode", "Ukendt");
  setText("systemsOnline", "Ukendt");
  setText("incidentCount", "Ukendt");
}

function weatherDescription(condition) {
  return weatherConditions[condition] || weatherConditions.exceptional;
}

function rainProbability(forecast) {
  const first = Array.isArray(forecast) ? forecast[0] : null;
  const value = Number(first?.precipitation_probability);
  return Number.isFinite(value) ? value : null;
}

function childRainText(probability) {
  if (probability === null) return "";
  if (probability >= 50) return "Der er stor chance for regn.";
  if (probability > 0) return "Der kan komme lidt regn.";
  return "Det ser tørt ud.";
}

function createForecastEntry(item) {
  const entry = document.createElement("li");
  entry.className = "weather-forecast-item";

  const day = document.createElement("span");
  day.className = "weather-forecast-day";
  const parsedDate = new Date(item.datetime || "");
  day.textContent = Number.isNaN(parsedDate.getTime())
    ? "Næste dag"
    : weekdayFormatter.format(parsedDate);

  const description = weatherDescription(item.condition);
  const symbol = document.createElement("span");
  symbol.className = "weather-forecast-symbol";
  symbol.setAttribute("role", "img");
  symbol.setAttribute("aria-label", description.label);
  symbol.textContent = description.symbol;

  const temperatures = document.createElement("span");
  temperatures.className = "weather-forecast-temperatures";
  const high = measurement(item.temperature_high, "°");
  const low = measurement(item.temperature_low, "°");
  temperatures.textContent = `${high} / ${low}`;

  entry.append(day, symbol, temperatures);

  const probability = Number(item.precipitation_probability);
  if (Number.isFinite(probability)) {
    const rain = document.createElement("span");
    rain.className = "weather-forecast-rain";
    rain.textContent = `${probability.toFixed(0)} % regn`;
    entry.append(rain);
  }

  return entry;
}

function applyWeatherRolePresentation(forecast) {
  const visibleDetails = {
    owner: new Set(["apparent", "humidity", "wind", "rain"]),
    adult: new Set(["apparent", "rain"]),
    anonymous: new Set(),
    child: new Set(),
    wall_display: new Set(),
  }[pageRole] || new Set();

  const measurements = document.getElementById("weatherMeasurements");
  document.querySelectorAll("[data-weather-detail]").forEach((element) => {
    element.hidden = !visibleDetails.has(element.dataset.weatherDetail);
  });
  if (measurements) measurements.hidden = visibleDetails.size === 0;

  const childSummary = document.getElementById("weatherChildRain");
  if (childSummary) {
    const childText = childRainText(rainProbability(forecast));
    childSummary.textContent = childText;
    childSummary.hidden = pageRole !== "child" || !childText;
  }
}

function renderWeatherState(message) {
  const state = document.getElementById("weatherState");
  const data = document.getElementById("weatherData");
  if (state) {
    state.textContent = message;
    state.hidden = false;
  }
  if (data) data.hidden = true;
}

function renderWeather(weather) {
  if (weather.status === "not_configured") {
    renderWeatherState("Ikke tilsluttet endnu");
    return;
  }
  if (weather.status === "unavailable") {
    renderWeatherState("Vejret kan ikke hentes lige nu");
    return;
  }

  const state = document.getElementById("weatherState");
  const data = document.getElementById("weatherData");
  if (state) state.hidden = true;
  if (data) data.hidden = false;

  const description = weatherDescription(weather.condition);
  setText("weatherSymbol", description.symbol);
  setText("weatherCardIcon", description.symbol);
  setText("weatherCondition", description.label);
  const symbol = document.getElementById("weatherSymbol");
  if (symbol) symbol.setAttribute("aria-label", description.label);

  setText("weatherTemperature", measurement(weather.temperature, weather.temperature_unit || ""));
  setText("weatherApparent", measurement(weather.apparent_temperature, weather.temperature_unit || ""));
  setText("weatherHumidity", measurement(weather.humidity, "%"));
  setText("weatherWind", measurement(weather.wind_speed, weather.wind_speed_unit || ""));

  const probability = rainProbability(weather.forecast);
  setText("weatherRain", probability === null ? "–" : `${probability.toFixed(0)} %`);

  const forecast = document.getElementById("weatherForecast");
  if (forecast) {
    forecast.replaceChildren();
    (weather.forecast || []).slice(0, 3).forEach((item) => {
      forecast.append(createForecastEntry(item));
    });
  }

  applyWeatherRolePresentation(weather.forecast || []);
  const stale = document.getElementById("weatherStale");
  if (stale) stale.hidden = weather.status !== "stale";
}

async function refreshMission() {
  try {
    const response = await fetch("/api/mission");
    if (!response.ok) throw new Error("Status kunne ikke hentes");
    renderMission(await response.json());
  } catch (error) {
    renderUnavailable();
  }
}

async function refreshWeather() {
  try {
    const response = await fetch("/api/family/weather");
    if (!response.ok) throw new Error("Vejret kunne ikke hentes");
    renderWeather(await response.json());
  } catch (error) {
    renderWeatherState("Vejret kan ikke hentes lige nu");
  }
}

async function refreshOwnerHealth() {
  if (pageRole !== "owner") return;
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("Systemstatus kunne ikke hentes");
    renderHealth(await response.json());
  } catch (error) {
    setText("cpuMetric", "–");
    setText("memoryMetric", "–");
    setText("diskMetric", "–");
  }
}

function refreshFamilyDashboard() {
  refreshMission();
  refreshWeather();
  refreshOwnerHealth();
}

updateClock();
refreshFamilyDashboard();
setInterval(updateClock, 1000);
setInterval(refreshFamilyDashboard, 30000);
