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
const longWeekdayFormatter = new Intl.DateTimeFormat("da-DK", {
  weekday: "long",
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
const calendarColors = new Set(["green", "blue", "violet", "yellow"]);

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

function wallStatusLabel(status) {
  const labels = {
    ok: "OK",
    warning: "OBS",
    critical: "ALARM",
  };
  return labels[status] || "UKENDT";
}

function updateWallHomeStatus(status) {
  const badge = document.getElementById("wallHomeStatusBadge");
  const dot = document.getElementById("wallHomeStatusDot");
  if (!badge) return;
  const safeStatus = ["ok", "warning", "critical"].includes(status) ? status : "unknown";
  badge.className = `wall-home-status ${safeStatus}`;
  if (dot) dot.className = `wall-home-status-dot ${safeStatus}`;
  setText("wallHomeStatusText", wallStatusLabel(safeStatus));
  badge.setAttribute("aria-label", calmStatus(safeStatus));
  badge.title = calmStatus(safeStatus);
}

function renderMission(mission) {
  const status = mission.overall_status || "unknown";
  const dot = document.getElementById("jarvisStatusDot");
  setText("overallHomeStatus", calmStatus(status));
  setText("lastUpdated", timeFormatter.format(new Date()));
  setText("jarvisStatus", calmStatus(status));
  if (dot) dot.className = `status-dot ${status}`;
  updateWallHomeStatus(status);
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
  updateWallHomeStatus("critical");
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

function localDateKey(value, allDay = false) {
  if (allDay) return String(value || "").slice(0, 10);
  const parsed = new Date(value || "");
  if (Number.isNaN(parsed.getTime())) return "";
  const year = parsed.getFullYear();
  const month = String(parsed.getMonth() + 1).padStart(2, "0");
  const day = String(parsed.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function relativeDayLabel(value, allDay = false) {
  const key = localDateKey(value, allDay);
  if (!key) return "Kommende";
  const today = localDateKey(new Date().toISOString());
  const tomorrowDate = new Date();
  tomorrowDate.setDate(tomorrowDate.getDate() + 1);
  const tomorrow = localDateKey(tomorrowDate.toISOString());
  if (key === today) return "I dag";
  if (key === tomorrow) return "I morgen";
  return longWeekdayFormatter.format(new Date(`${key}T12:00:00`));
}

function formatEventTime(event) {
  if (event.all_day) return "Hele dagen";
  const start = new Date(event.start || "");
  const end = new Date(event.end || "");
  if (Number.isNaN(start.getTime())) return "Tidspunkt ukendt";
  const startText = timeFormatter.format(start);
  if (Number.isNaN(end.getTime())) return startText;
  return `${startText}–${timeFormatter.format(end)}`;
}

function createCalendarEntry(event) {
  const entry = document.createElement("li");
  entry.className = "calendar-event";

  const time = document.createElement("span");
  time.className = "calendar-event-time";
  time.textContent = formatEventTime(event);

  const content = document.createElement("div");
  const title = document.createElement("strong");
  title.className = "calendar-event-title";
  title.textContent = event.title || "Aftale";

  const calendar = document.createElement("span");
  calendar.className = "calendar-event-calendar";
  calendar.textContent = event.calendar || "Kalender";

  content.append(title, calendar);
  entry.append(time, content);

  if (event.color && calendarColors.has(event.color)) {
    entry.dataset.calendarColor = event.color;
  }

  return entry;
}

function groupEventsByDay(events) {
  const groups = [];
  const lookup = new Map();
  events.forEach((event) => {
    const key = localDateKey(event.start, event.all_day);
    if (!key) return;
    if (!lookup.has(key)) {
      lookup.set(key, []);
      groups.push({ key, events: lookup.get(key) });
    }
    lookup.get(key).push(event);
  });
  return groups;
}

function createDayGroup(group) {
  const item = document.createElement("li");
  item.className = "calendar-day-group";

  const heading = document.createElement("div");
  heading.className = "calendar-day-heading";
  const label = document.createElement("strong");
  label.textContent = relativeDayLabel(`${group.key}T12:00:00`);
  const date = document.createElement("span");
  date.textContent = new Intl.DateTimeFormat("da-DK", { day: "numeric", month: "short" }).format(new Date(`${group.key}T12:00:00`));
  heading.append(label, date);

  const list = document.createElement("ol");
  list.className = "calendar-day-events";
  group.events.forEach((event) => list.append(createCalendarEntry(event)));
  item.append(heading, list);
  return item;
}

function renderCalendarState(message) {
  const state = document.getElementById("calendarState");
  const data = document.getElementById("calendarData");
  if (state) {
    state.textContent = message;
    state.hidden = false;
  }
  if (data) data.hidden = true;
}

function renderCalendar(calendar) {
  if (calendar.status === "not_configured") {
    renderCalendarState("Ikke tilsluttet endnu");
    return;
  }
  if (calendar.status === "unavailable") {
    renderCalendarState("Kalenderen kan ikke hentes lige nu");
    return;
  }

  const state = document.getElementById("calendarState");
  const data = document.getElementById("calendarData");
  if (state) state.hidden = true;
  if (data) data.hidden = false;

  const events = Array.isArray(calendar.events) ? calendar.events : [];
  const eventsContainer = document.getElementById("calendarEvents");
  const empty = document.getElementById("calendarEmpty");
  if (eventsContainer) {
    eventsContainer.replaceChildren();
    const groups = groupEventsByDay(events.slice(0, 8));
    groups.forEach((group) => eventsContainer.append(createDayGroup(group)));
    eventsContainer.hidden = groups.length === 0;
  }
  if (empty) empty.hidden = events.length > 0;

  const todaySummary = document.getElementById("calendarTodaySummary");
  const nextSummary = document.getElementById("calendarNextSummary");
  const upcomingSummary = document.getElementById("calendarUpcomingSummary");
  const anonymousSummary = document.getElementById("calendarAnonymousSummary");
  if (anonymousSummary) {
    const todayKey = localDateKey(new Date().toISOString());
    const todayEvents = events.filter((event) => localDateKey(event.start, event.all_day) === todayKey);
    const nextEvent = events[0];
    todaySummary.textContent = todayEvents.length ? `${todayEvents.length} aftale${todayEvents.length === 1 ? "" : "r"} i dag` : "Ingen aftaler i dag";
    nextSummary.textContent = nextEvent ? `Næste: ${nextEvent.title || "Aftale"}` : "Ingen kommende aftaler";
    upcomingSummary.textContent = events.length ? `${events.length} aftale${events.length === 1 ? "" : "r"} i kalenderen` : "";
    anonymousSummary.hidden = pageRole !== "anonymous";
  }

  const legend = document.getElementById("calendarLegend");
  if (legend) {
    legend.replaceChildren();
    (calendar.calendars || []).forEach((item) => {
      const entry = document.createElement("li");
      entry.dataset.calendarColor = calendarColors.has(item.color) ? item.color : "green";
      const dot = document.createElement("span");
      dot.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.textContent = item.label || "Kalender";
      entry.append(dot, label);
      legend.append(entry);
    });
  }

  const notice = document.getElementById("calendarNotice");
  if (notice) {
    notice.hidden = calendar.status !== "stale";
    notice.textContent = calendar.status === "stale" ? "Viser senest hentede kalenderdata" : "";
  }
}

async function fetchJson(endpoint) {
  const response = await fetch(endpoint, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function refresh() {
  try {
    const [mission, weather, calendar, health] = await Promise.all([
      fetchJson("/api/mission"),
      fetchJson("/api/family/weather"),
      fetchJson("/api/family/calendar"),
      fetchJson("/api/health"),
    ]);
    renderMission(mission);
    renderWeather(weather);
    renderCalendar(calendar);
    renderHealth(health);
  } catch (error) {
    renderUnavailable();
    renderWeatherState("Kunne ikke hente vejr");
    renderCalendarState("Kunne ikke hente kalender");
  }
}

updateClock();
refresh();
setInterval(updateClock, 1000);
setInterval(refresh, 120000);
