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
  const parsed = allDay ? new Date(`${key}T12:00:00`) : new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Kommende" : longWeekdayFormatter.format(parsed);
}

function eventTimeText(event) {
  if (event.all_day) return "Hele dagen";
  const start = new Date(event.start || "");
  const end = new Date(event.end || "");
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return "Tidspunkt ukendt";
  return `${timeFormatter.format(start)}–${timeFormatter.format(end)}`;
}

function calendarMarker(color, label) {
  const marker = document.createElement("span");
  marker.className = `calendar-color-marker calendar-color-${calendarColors.has(color) ? color : "blue"}`;
  marker.setAttribute("aria-label", `${label}, farvemarkering`);
  marker.setAttribute("role", "img");
  return marker;
}

function createCalendarLegendItem(calendar) {
  const item = document.createElement("li");
  item.className = "calendar-legend-item";
  item.append(calendarMarker(calendar.color, calendar.label));
  const label = document.createElement("span");
  label.textContent = calendar.label;
  item.append(label);
  return item;
}

function createCalendarEvent(event) {
  const item = document.createElement("li");
  item.className = "calendar-event";

  const when = document.createElement("div");
  when.className = "calendar-event-when";
  const day = document.createElement("span");
  day.className = "calendar-event-day";
  day.textContent = relativeDayLabel(event.start, event.all_day);
  const time = document.createElement("span");
  time.className = "calendar-event-time";
  time.textContent = eventTimeText(event);
  when.append(day, time);

  const details = document.createElement("div");
  const title = document.createElement("p");
  title.className = "calendar-event-title";
  title.textContent = event.title || "Aftale";
  details.append(title);
  if (event.ongoing) {
    const status = document.createElement("p");
    status.className = "calendar-event-status";
    status.textContent = "I gang nu";
    details.append(status);
  }

  const attribution = document.createElement("span");
  attribution.className = "calendar-event-calendar";
  attribution.append(calendarMarker(event.calendar?.color, event.calendar?.label || "Kalender"));
  const attributionLabel = document.createElement("span");
  attributionLabel.textContent = event.calendar?.label || "Kalender";
  attribution.append(attributionLabel);

  item.append(when, details, attribution);
  return item;
}

function anonymousNextText(value) {
  if (!value) return "";
  const allDay = !String(value).includes("T");
  const day = relativeDayLabel(value, allDay).toLowerCase();
  if (allDay) return `Næste aftale ${day}, hele dagen`;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const time = timeFormatter.format(parsed);
  return day === "i dag" ? `Næste aftale kl. ${time}` : `Næste aftale ${day} kl. ${time}`;
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

function renderAnonymousCalendar(calendar) {
  const summary = document.getElementById("calendarAnonymousSummary");
  const legend = document.getElementById("calendarLegend");
  const events = document.getElementById("calendarEvents");
  const empty = document.getElementById("calendarEmpty");
  if (summary) summary.hidden = false;
  if (legend) legend.hidden = true;
  if (events) events.hidden = true;
  if (empty) empty.hidden = true;

  const todayCount = Number(calendar.today_count) || 0;
  setText("calendarTodaySummary", todayCount === 0
    ? "Ingen aftaler i dag"
    : `${todayCount} ${todayCount === 1 ? "aftale" : "aftaler"} i dag`);
  setText("calendarNextSummary", anonymousNextText(calendar.next_event_start));
  const upcomingCount = Number(calendar.upcoming_count) || 0;
  setText("calendarUpcomingSummary", upcomingCount === 0
    ? "Ingen aftaler i perioden"
    : `${upcomingCount} ${upcomingCount === 1 ? "aftale" : "aftaler"} i den næste uge`);
}

function renderAuthenticatedCalendar(calendar) {
  const summary = document.getElementById("calendarAnonymousSummary");
  const legend = document.getElementById("calendarLegend");
  const events = document.getElementById("calendarEvents");
  const empty = document.getElementById("calendarEmpty");
  if (summary) summary.hidden = true;
  if (legend) {
    legend.hidden = false;
    legend.replaceChildren();
    (calendar.calendars || []).forEach((item) => legend.append(createCalendarLegendItem(item)));
  }
  if (events) {
    events.hidden = false;
    events.replaceChildren();
    (calendar.events || []).forEach((event) => events.append(createCalendarEvent(event)));
  }
  if (empty) empty.hidden = (calendar.events || []).length !== 0;
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

  if (pageRole === "anonymous") renderAnonymousCalendar(calendar);
  else renderAuthenticatedCalendar(calendar);

  const notice = document.getElementById("calendarNotice");
  if (notice) {
    const messages = {
      partial: "Nogle kalendere kunne ikke hentes",
      stale: "Viser senest hentede kalenderdata",
    };
    notice.textContent = messages[calendar.status] || "";
    notice.hidden = !messages[calendar.status];
  }
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

async function refreshCalendar() {
  try {
    const response = await fetch("/api/family/calendar");
    if (!response.ok) throw new Error("Kalenderen kunne ikke hentes");
    renderCalendar(await response.json());
  } catch (error) {
    renderCalendarState("Kalenderen kan ikke hentes lige nu");
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
  refreshCalendar();
  refreshOwnerHealth();
}

updateClock();
refreshFamilyDashboard();
setInterval(updateClock, 1000);
setInterval(refreshFamilyDashboard, 30000);
