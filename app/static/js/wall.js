const wallRoutineIds = new Set(["morning", "evening"]);
const wallRoutineEndpoints = {
  morning: {
    complete: "/api/family/routines/morning/complete",
    back: "/api/family/routines/morning/back",
  },
  evening: {
    complete: "/api/family/routines/evening/complete",
    back: "/api/family/routines/evening/back",
  },
};
const wallPictograms = new Set([
  "wake", "tv", "breakfast", "clothes", "teeth", "tablet", "outerwear",
  "school", "homework", "exercise", "play", "dinner", "cleanup", "bath",
  "laundry", "bed", "audio", "sleep", "complete",
]);
const wallCalendarColors = new Set(["green", "blue", "violet", "yellow"]);
const weatherStates = new Set(["ok", "stale", "not_configured", "unavailable"]);
const calendarStates = new Set(["ok", "partial", "stale", "not_configured", "unavailable"]);
const weatherMap = {
  "clear-night": ["Klart", "🌙"],
  cloudy: ["Skyet", "☁️"],
  fog: ["Tåge", "🌫️"],
  hail: ["Hagl", "🌨️"],
  lightning: ["Torden", "⚡"],
  "lightning-rainy": ["Tordenbyger", "⛈️"],
  partlycloudy: ["Delvist skyet", "⛅"],
  pouring: ["Kraftig regn", "🌧️"],
  rainy: ["Regn", "🌧️"],
  snowy: ["Sne", "❄️"],
  "snowy-rainy": ["Slud", "🌨️"],
  sunny: ["Solrigt", "☀️"],
  windy: ["Blæsende", "💨"],
  "windy-variant": ["Blæsende og skyet", "🌬️"],
  exceptional: ["Usædvanligt vejr", "🌡️"],
};

let wallCsrf = null;
let wallRoutineState = null;
let wallActiveRoutine = null;
let wallRoutineBusy = false;
const inFlight = { weather: false, calendar: false, routines: false };

function el(id) {
  return document.getElementById(id);
}

function text(id, value) {
  const node = el(id);
  if (node) {
    node.textContent = value;
  }
}

const dateFormat = new Intl.DateTimeFormat("da-DK", {
  weekday: "long",
  day: "numeric",
  month: "long",
});
const timeFormat = new Intl.DateTimeFormat("da-DK", {
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const weekdayFormat = new Intl.DateTimeFormat("da-DK", { weekday: "long" });

function updateWallClock() {
  const now = new Date();
  text("wallClock", timeFormat.format(now));
  text("wallDate", dateFormat.format(now));
}

function finiteNumber(value) {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function numberText(value, unit = "") {
  const number = finiteNumber(value);
  if (number === null) {
    return "–";
  }
  return `${Number.isInteger(number) ? number : number.toFixed(1)}${unit}`;
}

function apparentTemperatureText(value, unit = "") {
  const number = finiteNumber(value);
  return number === null ? "" : `Føles som ${numberText(number, unit)}`;
}

function validUvIndex(value) {
  const number = finiteNumber(value);
  return number !== null && number >= 0 ? number : null;
}

function uvCategory(value) {
  if (value < 3) return "Lav";
  if (value < 6) return "Moderat";
  if (value < 8) return "Høj";
  if (value < 11) return "Meget høj";
  return "Ekstrem";
}

function renderUvIndex(value) {
  const node = el("wallUvIndex");
  if (!node) return;

  const number = validUvIndex(value);
  node.hidden = number === null;
  if (number === null) {
    node.textContent = "";
    return;
  }
  node.textContent = `UV ${numberText(number)} · ${uvCategory(number)}`;
}

function weatherDescription(condition) {
  return weatherMap[condition] || weatherMap.exceptional;
}

function notice(message, state = "") {
  text("wallGlobalNotice", message);
  const node = el("wallGlobalNotice");
  if (node) node.dataset.state = state;
}

async function safeJson(response) {
  if (!response.ok) throw new Error("request failed");
  return response.json();
}

async function loadWeather() {
  if (inFlight.weather || document.hidden) return;
  inFlight.weather = true;
  try {
    const data = await safeJson(await fetch("/api/family/weather"));
    if (!weatherStates.has(data.status)) throw new Error("invalid status");

    if (data.status === "not_configured") {
      renderUvIndex(null);
      text("wallWeatherCondition", "Vejret er ikke tilsluttet");
      return;
    }
    if (data.status === "unavailable") {
      renderUvIndex(null);
      text("wallWeatherCondition", "Vejret kan ikke hentes lige nu");
      return;
    }

    const description = weatherDescription(data.condition);
    text("wallWeatherIcon", description[1]);
    el("wallWeatherIcon")?.setAttribute("aria-label", description[0]);
    text("wallWeatherHeading", numberText(data.temperature, data.temperature_unit || ""));
    text("wallWeatherCondition", description[0]);
    text(
      "wallWeatherApparent",
      apparentTemperatureText(data.apparent_temperature, data.temperature_unit || ""),
    );
    renderUvIndex(data.uv_index);

    const forecast = el("wallForecast");
    if (forecast) {
      forecast.replaceChildren();
      (data.forecast || []).slice(0, 3).forEach((item) => {
        const li = document.createElement("li");
        li.className = "wall-forecast-item";

        const day = document.createElement("span");
        day.className = "wall-forecast-day";
        const parsed = new Date(item.datetime || "");
        day.textContent = Number.isNaN(parsed.getTime())
          ? "Næste dag"
          : weekdayFormat.format(parsed);

        const icon = document.createElement("span");
        icon.className = "wall-forecast-icon";
        const info = weatherDescription(item.condition);
        icon.textContent = info[1];
        icon.setAttribute("role", "img");
        icon.setAttribute("aria-label", info[0]);

        const temperatures = document.createElement("span");
        temperatures.className = "wall-forecast-temp";
        temperatures.textContent = `${numberText(item.temperature_high, "°")} / ${numberText(item.temperature_low, "°")}`;

        li.append(day, icon, temperatures);
        forecast.append(li);
      });
    }

    if (data.status === "stale") {
      notice("Viser senest hentede vejrdata", "warning");
    }
  } catch (error) {
    notice("Nogle oplysninger kunne ikke opdateres.", "warning");
  } finally {
    inFlight.weather = false;
  }
}

function localDateKey(value, allDay = false) {
  if (allDay) return String(value || "").slice(0, 10);
  const date = value instanceof Date ? value : new Date(value || "");
  if (Number.isNaN(date.getTime())) return "";
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function dateFromKey(key) {
  const parts = String(key).split("-").map(Number);
  if (parts.length !== 3 || !parts.every(Number.isFinite)) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function todayKey(now = new Date()) {
  return localDateKey(now);
}

function tomorrowKey(now = new Date()) {
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  return localDateKey(tomorrow);
}

function eventBounds(event) {
  if (!event || typeof event !== "object") return null;

  if (event.all_day) {
    const start = dateFromKey(event.start);
    const end = dateFromKey(event.end);
    return start && end && end > start ? { start, end } : null;
  }

  const start = new Date(event.start || "");
  const end = new Date(event.end || "");
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
    return null;
  }
  return { start, end };
}

function eventIntersectsDate(event, key) {
  const bounds = eventBounds(event);
  const start = dateFromKey(key);
  if (!bounds || !start) return false;
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return bounds.start < end && bounds.end > start;
}

function eventIsCurrentOrFuture(event, now) {
  const bounds = eventBounds(event);
  return Boolean(bounds && bounds.end > now);
}

function compareAppointmentCandidates(left, right) {
  const leftBounds = eventBounds(left);
  const rightBounds = eventBounds(right);
  if (!leftBounds && !rightBounds) return 0;
  if (!leftBounds) return 1;
  if (!rightBounds) return -1;

  const startDifference = leftBounds.start.getTime() - rightBounds.start.getTime();
  if (startDifference !== 0) return startDifference;

  const endDifference = leftBounds.end.getTime() - rightBounds.end.getTime();
  if (endDifference !== 0) return endDifference;

  return String(left.title || "").localeCompare(String(right.title || ""), "da-DK");
}

function selectNextAppointment(events, now = new Date()) {
  const list = Array.isArray(events) ? events : [];
  const today = todayKey(now);
  const tomorrow = tomorrowKey(now);

  const remainingToday = list
    .filter((event) => eventIntersectsDate(event, today) && eventIsCurrentOrFuture(event, now))
    .sort(compareAppointmentCandidates);
  if (remainingToday.length > 0) {
    return { event: remainingToday[0], day: "today" };
  }

  const tomorrowEvents = list
    .filter((event) => eventIntersectsDate(event, tomorrow))
    .sort(compareAppointmentCandidates);
  return tomorrowEvents.length > 0
    ? { event: tomorrowEvents[0], day: "tomorrow" }
    : null;
}

function eventTime(event, now = new Date()) {
  const bounds = eventBounds(event);
  if (bounds && !event.all_day && bounds.start <= now && now < bounds.end) {
    return "I gang nu";
  }
  if (event.ongoing) return "I gang nu";
  if (event.all_day) return "Hele dagen";
  return bounds ? timeFormat.format(bounds.start) : "";
}

function appendEvent(list, event) {
  const row = document.createElement("li");
  const color = wallCalendarColors.has(event.calendar?.color) ? event.calendar.color : "";
  row.className = `wall-event-row${color ? ` calendar-color-${color}` : ""}`;

  const time = document.createElement("span");
  time.className = "wall-event-time";
  time.textContent = eventTime(event);

  const title = document.createElement("span");
  title.className = "wall-event-title";
  title.textContent = event.title || "Aftale";

  const calendar = document.createElement("span");
  calendar.className = "wall-event-calendar";
  calendar.textContent = event.calendar?.label || "Kalender";

  row.append(time, title, calendar);
  list.append(row);
}

function renderNextAppointment(selection, now = new Date()) {
  const event = selection?.event || null;
  const container = el("wallNextEvent");
  if (container) {
    container.className = "wall-next-event";
    const color = event && wallCalendarColors.has(event.calendar?.color)
      ? event.calendar.color
      : "";
    if (color) container.classList.add(`calendar-color-${color}`);
  }

  text("wallNextDay", selection?.day === "tomorrow" ? "I morgen" : "");
  text("wallNextTime", event ? eventTime(event, now) : "");
  text("wallNextTitle", event?.title || "Ingen aftaler i dag eller i morgen");
  text("wallNextCalendar", event?.calendar?.label || "");
}

async function loadCalendar() {
  if (inFlight.calendar || document.hidden) return;
  inFlight.calendar = true;
  try {
    const data = await safeJson(await fetch("/api/family/calendar"));
    if (!calendarStates.has(data.status)) throw new Error("invalid status");

    if (data.status === "not_configured" || data.status === "unavailable") {
      text(
        "wallCalendarNotice",
        data.status === "not_configured"
          ? "Kalender er ikke tilsluttet"
          : "Kalender kan ikke hentes lige nu",
      );
      return;
    }

    const events = Array.isArray(data.events) ? data.events : [];
    const now = new Date();
    const today = events.filter((event) => eventIntersectsDate(event, todayKey(now)));
    const list = el("wallTodayEvents");
    if (list) {
      list.replaceChildren();
      today.forEach((event) => appendEvent(list, event));
    }

    const empty = el("wallNoEvents");
    if (empty) empty.hidden = today.length > 0;

    renderNextAppointment(selectNextAppointment(events, now), now);
    text(
      "wallCalendarNotice",
      data.status === "partial"
        ? "Nogle kalendere kunne ikke hentes"
        : data.status === "stale"
          ? "Viser senest hentede kalender"
          : "",
    );
  } catch (error) {
    text("wallCalendarNotice", "Kalenderen kunne ikke opdateres");
  } finally {
    inFlight.calendar = false;
  }
}

function setRoutineBusy(value) {
  wallRoutineBusy = value;
  document
    .querySelectorAll("[data-wall-routine],#wallRoutineComplete,#wallRoutineBack")
    .forEach((button) => {
      button.disabled = value;
    });
}

function setRoutinePictogram(key, label) {
  const safe = wallPictograms.has(key) ? key : "complete";
  el("wallRoutinePictogramUse")?.setAttribute(
    "href",
    `/static/pictograms/routines.svg#${safe}`,
  );
  el("wallRoutinePictogram")?.setAttribute("aria-label", label);
}

function renderRoutine() {
  if (!wallRoutineState?.routines) return;
  if (!wallRoutineIds.has(wallActiveRoutine)) {
    wallActiveRoutine = wallRoutineState.recommended;
  }

  const routine = wallRoutineState.routines[wallActiveRoutine];
  if (!routine) return;

  document.querySelectorAll("[data-wall-routine]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.wallRoutine === wallActiveRoutine));
  });
  text("wallRoutineLabel", routine.label);
  text(
    "wallRoutineProgress",
    routine.completed
      ? `${routine.total} trin færdige`
      : `Trin ${routine.current_index + 1} af ${routine.total}`,
  );

  if (routine.completed) {
    text("wallRoutineTitle", "Godt klaret!");
    setRoutinePictogram("complete", "Godt klaret");
    el("wallRoutineComplete").hidden = true;
  } else {
    text("wallRoutineTitle", routine.current_task?.title || "Næste trin");
    setRoutinePictogram(
      routine.current_task?.pictogram,
      routine.current_task?.title || "Rutinepiktogram",
    );
    el("wallRoutineComplete").hidden = false;
  }
  el("wallRoutineBack").disabled = wallRoutineBusy || routine.current_index === 0;
}

async function loadRoutines() {
  if (inFlight.routines || document.hidden) return;
  inFlight.routines = true;
  try {
    wallRoutineState = await safeJson(await fetch("/api/family/routines"));
    if (!wallActiveRoutine) wallActiveRoutine = wallRoutineState.recommended;
    renderRoutine();
  } catch (error) {
    text("wallRoutineMessage", "Rutinen kunne ikke opdateres");
  } finally {
    inFlight.routines = false;
  }
}

async function csrfToken() {
  if (wallCsrf) return wallCsrf;
  const profile = await safeJson(await fetch("/api/auth/me"));
  wallCsrf = profile.csrf_token;
  return wallCsrf;
}

async function changeRoutine(action) {
  if (wallRoutineBusy || !wallRoutineIds.has(wallActiveRoutine)) return;
  const routine = wallRoutineState?.routines?.[wallActiveRoutine];
  if (!routine) return;

  setRoutineBusy(true);
  text("wallRoutineMessage", "Gemmer…");
  try {
    const response = await fetch(wallRoutineEndpoints[wallActiveRoutine][action], {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": await csrfToken(),
      },
      body: JSON.stringify({ expected_index: routine.current_index }),
    });
    wallRoutineState = await safeJson(response);
    text("wallRoutineMessage", "");
    renderRoutine();
  } catch (error) {
    text("wallRoutineMessage", "Prøv igen om lidt.");
  } finally {
    setRoutineBusy(false);
    renderRoutine();
  }
}

async function logout() {
  try {
    await fetch("/api/auth/logout", {
      method: "POST",
      headers: { "X-CSRF-Token": await csrfToken() },
    });
  } finally {
    window.location.assign("/login");
  }
}

function refreshVisible() {
  if (document.hidden) return;
  loadWeather();
  loadCalendar();
  loadRoutines();
}

document.querySelectorAll("[data-wall-routine]").forEach((button) => {
  button.addEventListener("click", () => {
    if (wallRoutineIds.has(button.dataset.wallRoutine) && !wallRoutineBusy) {
      wallActiveRoutine = button.dataset.wallRoutine;
      renderRoutine();
    }
  });
});
el("wallRoutineComplete")?.addEventListener("click", () => changeRoutine("complete"));
el("wallRoutineBack")?.addEventListener("click", () => changeRoutine("back"));
el("wallLogout")?.addEventListener("click", logout);

const fullscreenButton = el("wallFullscreen");
if (!document.documentElement.requestFullscreen || !document.exitFullscreen) {
  if (fullscreenButton) fullscreenButton.hidden = true;
} else {
  fullscreenButton?.addEventListener("click", async () => {
    if (!document.fullscreenElement) {
      await document.documentElement.requestFullscreen();
    } else {
      await document.exitFullscreen();
    }
  });
  document.addEventListener("fullscreenchange", () => {
    if (!fullscreenButton) return;
    fullscreenButton.textContent = document.fullscreenElement
      ? "Afslut fuld skærm"
      : "Fuld skærm";
    fullscreenButton.classList.toggle("is-fullscreen", Boolean(document.fullscreenElement));
  });
}

document.addEventListener("visibilitychange", refreshVisible);
updateWallClock();
refreshVisible();
setInterval(updateWallClock, 30000);
setInterval(loadWeather, 300000);
setInterval(loadCalendar, 120000);
setInterval(loadRoutines, 45000);
