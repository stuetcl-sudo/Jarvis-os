selectNextAppointment = function selectTomorrowAppointment(events, now = new Date()) {
  const list = Array.isArray(events) ? events : [];
  const tomorrow = tomorrowKey(now);
  const candidates = list
    .filter((event) => eventIntersectsDate(event, tomorrow))
    .sort(compareAppointmentCandidates);
  return candidates.length > 0
    ? { event: candidates[0], day: "tomorrow" }
    : null;
};

renderNextAppointment = function renderTomorrowAppointment(selection, now = new Date()) {
  const event = selection?.event || null;
  const container = el("wallNextEvent");
  if (container) {
    container.className = "wall-next-event";
    const color = event && wallCalendarColors.has(event.calendar?.color)
      ? event.calendar.color
      : "";
    if (color) container.classList.add(`calendar-color-${color}`);
  }

  text("wallNextDay", event ? "Første aftale" : "");
  text("wallNextTime", event ? eventTime(event, now) : "");
  text("wallNextTitle", event?.title || "Ingen aftaler i morgen");
  text("wallNextCalendar", event?.calendar?.label || "");
};
