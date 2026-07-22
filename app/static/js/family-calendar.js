const calendarDayChoices = new Set([1, 3, 5, 7]);
const calendarDateFormatter = new Intl.DateTimeFormat("da-DK", {
  day: "numeric",
  month: "short",
});

let calendarVisibleDays = 3;
let latestCalendarSnapshot = null;

function calendarKeyFromDate(date) {
  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-");
}

function calendarDateFromKey(key) {
  const parts = String(key).split("-").map(Number);
  if (parts.length !== 3 || !parts.every(Number.isFinite)) return null;
  return new Date(parts[0], parts[1] - 1, parts[2]);
}

function calendarRangeKeys(days, now = new Date()) {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12, 0, 0);
  return Array.from({ length: days }, (_, index) => {
    const date = new Date(start);
    date.setDate(date.getDate() + index);
    return calendarKeyFromDate(date);
  });
}

function calendarEventBounds(event) {
  if (!event || typeof event !== "object") return null;
  if (event.all_day) {
    const start = calendarDateFromKey(event.start);
    const end = calendarDateFromKey(event.end);
    return start && end && end > start ? { start, end } : null;
  }
  const start = new Date(event.start || "");
  const end = new Date(event.end || "");
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) return null;
  return { start, end };
}

function calendarEventIsCurrentOrUpcoming(event, now = new Date()) {
  const bounds = calendarEventBounds(event);
  return Boolean(bounds && bounds.end > now);
}

function calendarEventIntersectsDay(event, key) {
  const bounds = calendarEventBounds(event);
  const day = calendarDateFromKey(key);
  if (!bounds || !day) return false;
  const start = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return bounds.start < end && bounds.end > start;
}

function calendarRangeDisplayName(value) {
  if (typeof calendarDisplayName === "function") return calendarDisplayName(value);
  if (typeof value === "string" && value.trim()) return value.trim();
  if (value && typeof value === "object") {
    const candidate = value.label || value.name || value.summary || value.title;
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
  }
  return "Kalender";
}

function createCalendarRangeLegendItem(item) {
  if (typeof createCalendarLegendItem === "function") return createCalendarLegendItem(item);
  const entry = document.createElement("li");
  const color = calendarColors.has(item?.color) ? item.color : "green";
  entry.className = "calendar-legend-item";
  entry.dataset.calendarColor = color;

  const marker = document.createElement("span");
  marker.className = `calendar-color-marker calendar-color-${color}`;
  marker.setAttribute("aria-hidden", "true");

  const label = document.createElement("span");
  label.textContent = calendarRangeDisplayName(item);

  entry.append(marker, label);
  return entry;
}

function calendarDayTitle(key, index) {
  if (index === 0) return "I dag";
  if (index === 1) return "I morgen";
  const date = calendarDateFromKey(key);
  return date ? longWeekdayFormatter.format(date) : "Kommende";
}

function createCalendarDayGroup(key, index, dayEvents) {
  const group = document.createElement("li");
  group.className = "calendar-day-group";

  const header = document.createElement("header");
  header.className = "calendar-day-heading";
  const title = document.createElement("h3");
  title.textContent = calendarDayTitle(key, index);
  const date = document.createElement("time");
  const parsed = calendarDateFromKey(key);
  date.dateTime = key;
  date.textContent = parsed ? calendarDateFormatter.format(parsed) : key;
  header.append(title, date);

  const list = document.createElement("ol");
  list.className = "calendar-day-events";
  list.setAttribute("aria-label", `${title.textContent}, ${date.textContent}`);

  if (dayEvents.length === 0) {
    const empty = document.createElement("li");
    empty.className = "calendar-day-empty";
    empty.textContent = index === 0 ? "Ingen aftaler i dag" : "Ingen aftaler";
    list.append(empty);
  } else {
    dayEvents.forEach((event) => list.append(createCalendarEvent(event)));
  }

  group.append(header, list);
  return group;
}

function updateCalendarLayoutState() {
  document.body.dataset.calendarDays = String(calendarVisibleDays);
}

function updateCalendarRangeButtons() {
  document.querySelectorAll("[data-calendar-days]").forEach((button) => {
    const days = Number(button.dataset.calendarDays);
    const selected = days === calendarVisibleDays;
    button.setAttribute("aria-pressed", String(selected));
    button.classList.toggle("is-selected", selected);
  });
  updateCalendarLayoutState();
}

function renderCalendarDays(calendar) {
  const now = new Date();
  const events = Array.isArray(calendar.events)
    ? calendar.events.filter((event) => calendarEventIsCurrentOrUpcoming(event, now))
    : [];
  const container = document.getElementById("calendarEvents");
  if (!container) return;

  const keys = calendarRangeKeys(calendarVisibleDays, now);
  container.className = `calendar-events calendar-days-${calendarVisibleDays}`;
  container.setAttribute("aria-label", `Familiens aftaler for ${calendarVisibleDays} dage`);
  container.replaceChildren();
  keys.forEach((key, index) => {
    const dayEvents = events.filter((event) => calendarEventIntersectsDay(event, key));
    container.append(createCalendarDayGroup(key, index, dayEvents));
  });

  const empty = document.getElementById("calendarEmpty");
  if (empty) empty.hidden = true;
  updateCalendarRangeButtons();
}

renderAuthenticatedCalendar = function renderAuthenticatedCalendarRange(calendar) {
  latestCalendarSnapshot = calendar;
  window.dispatchEvent(
    new CustomEvent("jarvis:calendar-updated", {
      detail: calendar,
    }),
  );
  const summary = document.getElementById("calendarAnonymousSummary");
  const legend = document.getElementById("calendarLegend");
  const events = document.getElementById("calendarEvents");
  const controls = document.getElementById("calendarRangeControls");

  if (summary) summary.hidden = true;
  if (controls) controls.hidden = false;
  if (legend) {
    legend.hidden = false;
    legend.replaceChildren();
    (calendar.calendars || []).forEach((item) => legend.append(createCalendarRangeLegendItem(item)));
  }
  if (events) events.hidden = false;
  renderCalendarDays(calendar);
};

document.querySelectorAll("[data-calendar-days]").forEach((button) => {
  button.addEventListener("click", () => {
    const days = Number(button.dataset.calendarDays);
    if (!calendarDayChoices.has(days) || days === calendarVisibleDays) return;
    calendarVisibleDays = days;
    updateCalendarRangeButtons();
    if (latestCalendarSnapshot) renderCalendarDays(latestCalendarSnapshot);
  });
});

const calendarRangeControls = document.getElementById("calendarRangeControls");
if (calendarRangeControls) calendarRangeControls.hidden = pageRole === "anonymous";
updateCalendarRangeButtons();
setInterval(() => {
  if (latestCalendarSnapshot) renderCalendarDays(latestCalendarSnapshot);
}, 30000);
