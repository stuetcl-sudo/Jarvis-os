const editorRoutineIds = new Set(["morning", "evening"]);
const editorEndpoints = {
  definitions: "/api/family/routines/definitions",
  morning: {
    save: "/api/family/routines/definitions/morning",
    reset: "/api/family/routines/definitions/morning/reset-default",
  },
  evening: {
    save: "/api/family/routines/definitions/evening",
    reset: "/api/family/routines/definitions/evening/reset-default",
  },
};
const editorPictogramKeys = new Set([
  "wake", "tv", "breakfast", "clothes", "teeth", "tablet", "outerwear", "school",
  "homework", "exercise", "play", "dinner", "cleanup", "bath", "laundry", "bed",
  "audio", "sleep", "complete",
]);

let routineEditorData = null;
let routineEditorDraft = null;
let routineEditorId = "morning";
let routineEditorDirty = false;
let routineEditorPending = false;
let routineEditorPersonId = null;
let routineEditorPersonName = "";
let draggedTaskIndex = null;

function editorElement(id) {
  return document.getElementById(id);
}

function editorMessage(value) {
  const element = editorElement("routineEditorMessage");
  if (element) element.textContent = value;
}

function editorSetPending(pending) {
  routineEditorPending = pending;
  document.querySelectorAll("#routineEditor button, #routineEditor input").forEach((element) => {
    element.disabled = pending;
  });
}

function cloneRoutine(value) {
  return JSON.parse(JSON.stringify(value));
}

function editorPersonQuery() {
  return routineEditorPersonId
    ? `?person_id=${encodeURIComponent(routineEditorPersonId)}`
    : "";
}

function syncRoutineEditorPerson(data) {
  routineEditorPersonId = data?.selected_person_id || activePersonId || null;
  const people = Array.isArray(data?.persons) ? data.persons : [];
  const selected = people.find((person) => person.user_id === routineEditorPersonId);
  routineEditorPersonName = selected?.display_name || "valgt person";
}

function localPictogram(key, label) {
  const safeKey = editorPictogramKeys.has(key) ? key : "complete";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label);
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `/static/pictograms/routines.svg#${safeKey}`);
  svg.append(use);
  return svg;
}

function markEditorDirty() {
  routineEditorDirty = true;
  editorMessage("Ikke gemte ændringer");
}

function moveEditorTask(index, direction) {
  const target = index + direction;
  if (!routineEditorDraft || target < 0 || target >= routineEditorDraft.tasks.length) return;
  const [task] = routineEditorDraft.tasks.splice(index, 1);
  routineEditorDraft.tasks.splice(target, 0, task);
  markEditorDirty();
  renderRoutineEditor();
}

function createWeekdayControls(task) {
  const wrapper = document.createElement("fieldset");
  wrapper.className = "routine-weekdays";
  const legend = document.createElement("legend");
  legend.textContent = "Vises på";
  wrapper.append(legend);
  const allDays = document.createElement("span");
  allDays.textContent = task.weekdays.length ? "" : "Hver dag";
  wrapper.append(allDays);
  routineEditorData.weekdays.forEach((weekday) => {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = task.weekdays.includes(weekday.key);
    input.addEventListener("change", () => {
      const values = new Set(task.weekdays);
      if (input.checked) values.add(weekday.key);
      else values.delete(weekday.key);
      task.weekdays = Array.from(values).sort((a, b) => a - b);
      markEditorDirty();
      renderRoutineEditor();
    });
    const text = document.createElement("span");
    text.textContent = weekday.label;
    label.append(input, text);
    wrapper.append(label);
  });
  return wrapper;
}

function createPictogramPicker(task) {
  const picker = document.createElement("div");
  picker.className = "routine-picker";
  routineEditorData.pictograms.forEach((item) => {
    if (!editorPictogramKeys.has(item.key)) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "routine-picker-option";
    button.setAttribute("aria-pressed", String(task.pictogram === item.key));
    button.append(localPictogram(item.key, item.label));
    const label = document.createElement("span");
    label.textContent = item.label;
    button.append(label);
    button.addEventListener("click", () => {
      task.pictogram = item.key;
      markEditorDirty();
      renderRoutineEditor();
    });
    picker.append(button);
  });
  return picker;
}

function createTaskEditor(task, index) {
  const item = document.createElement("li");
  item.className = "routine-task";
  item.draggable = true;
  item.addEventListener("dragstart", () => { draggedTaskIndex = index; });
  item.addEventListener("dragover", (event) => event.preventDefault());
  item.addEventListener("drop", (event) => {
    event.preventDefault();
    if (draggedTaskIndex === null || draggedTaskIndex === index) return;
    const [moved] = routineEditorDraft.tasks.splice(draggedTaskIndex, 1);
    routineEditorDraft.tasks.splice(index, 0, moved);
    draggedTaskIndex = null;
    markEditorDirty();
    renderRoutineEditor();
  });

  const top = document.createElement("div");
  top.className = "routine-task-top";
  const preview = document.createElement("div");
  preview.className = "routine-task-preview";
  preview.append(localPictogram(task.pictogram, task.title || "Piktogram"));

  const title = document.createElement("input");
  title.value = task.title;
  title.maxLength = 80;
  title.required = true;
  title.setAttribute("aria-label", `Titel for trin ${index + 1}`);
  title.addEventListener("input", () => { task.title = title.value; markEditorDirty(); });

  const actions = document.createElement("div");
  actions.className = "routine-task-actions";
  const up = document.createElement("button");
  up.type = "button";
  up.textContent = "Flyt op";
  up.disabled = index === 0;
  up.addEventListener("click", () => moveEditorTask(index, -1));
  const down = document.createElement("button");
  down.type = "button";
  down.textContent = "Flyt ned";
  down.disabled = index === routineEditorDraft.tasks.length - 1;
  down.addEventListener("click", () => moveEditorTask(index, 1));
  const remove = document.createElement("button");
  remove.type = "button";
  remove.textContent = "Slet";
  remove.addEventListener("click", () => {
    if (!window.confirm("Vil du slette dette trin?")) return;
    routineEditorDraft.tasks.splice(index, 1);
    markEditorDirty();
    renderRoutineEditor();
  });
  actions.append(up, down, remove);
  top.append(preview, title, actions);

  const grid = document.createElement("div");
  grid.className = "routine-task-grid";
  const timeLabel = document.createElement("label");
  timeLabel.className = "routine-editor-label";
  timeLabel.textContent = "Vejledende tidspunkt";
  const time = document.createElement("input");
  time.type = "time";
  time.value = task.time || "";
  time.addEventListener("input", () => { task.time = time.value || null; markEditorDirty(); });
  timeLabel.append(time);
  grid.append(createPictogramPicker(task), timeLabel);

  item.append(top, grid, createWeekdayControls(task));
  return item;
}

function renderRoutineEditor() {
  if (!routineEditorDraft || !routineEditorData) return;
  document.querySelectorAll("[data-editor-routine]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.editorRoutine === routineEditorId));
  });
  const label = editorElement("routineEditorLabel");
  if (label) label.value = routineEditorDraft.label;
  const list = editorElement("routineEditorList");
  if (list) {
    list.replaceChildren();
    routineEditorDraft.tasks.forEach((task, index) => list.append(createTaskEditor(task, index)));
  }
}

function switchEditorRoutine(routineId) {
  if (!editorRoutineIds.has(routineId)) return;
  if (routineEditorDirty && !window.confirm("Vil du kassere dine ikke gemte ændringer?")) return;
  routineEditorId = routineId;
  routineEditorDraft = cloneRoutine(routineEditorData.routines[routineId]);
  routineEditorDirty = false;
  editorMessage("");
  renderRoutineEditor();
}

async function editorCsrfToken() {
  if (typeof loadRoutineCsrfToken === "function") return loadRoutineCsrfToken();
  const response = await fetch("/api/auth/me", { credentials: "same-origin" });
  if (!response.ok) throw new Error("Login kræves");
  const profile = await response.json();
  return profile.csrf_token;
}

async function openRoutineEditor() {
  const dialog = editorElement("routineEditor");
  if (!dialog || routineEditorPending) return;
  editorSetPending(true);
  try {
    routineEditorPersonId = activePersonId || null;
    if (!routineEditorPersonId) throw new Error("Vælg en person først");
    const response = await fetch(
      `${editorEndpoints.definitions}${editorPersonQuery()}`,
      { credentials: "same-origin" },
    );
    if (!response.ok) throw new Error("Editor kunne ikke hentes");
    routineEditorData = await response.json();
    syncRoutineEditorPerson(routineEditorData);
    routineEditorId = activeRoutineId && editorRoutineIds.has(activeRoutineId) ? activeRoutineId : "morning";
    routineEditorDraft = cloneRoutine(routineEditorData.routines[routineEditorId]);
    routineEditorDirty = false;
    renderRoutineEditor();
    editorMessage(`Redigerer rutiner for ${routineEditorPersonName}.`);
    dialog.showModal();
  } catch (error) {
    editorMessage("Editor kunne ikke åbnes.");
  } finally {
    editorSetPending(false);
  }
}

function closeRoutineEditor() {
  const dialog = editorElement("routineEditor");
  if (!dialog) return;
  if (routineEditorDirty && !window.confirm("Vil du lukke uden at gemme?")) return;
  routineEditorDirty = false;
  dialog.close();
}

function normalizedEditorPayload() {
  return {
    label: routineEditorDraft.label,
    tasks: routineEditorDraft.tasks.map((task) => ({
      ...(task.id && !String(task.id).startsWith("draft_") ? { id: task.id } : {}),
      title: task.title,
      pictogram: task.pictogram,
      time: task.time || null,
      weekdays: Array.from(task.weekdays || []),
    })),
  };
}

async function saveRoutineEditor(event) {
  event.preventDefault();
  if (routineEditorPending || !editorRoutineIds.has(routineEditorId)) return;
  const label = editorElement("routineEditorLabel");
  routineEditorDraft.label = label ? label.value : routineEditorDraft.label;
  editorSetPending(true);
  editorMessage("Gemmer…");
  try {
    const csrf = await editorCsrfToken();
    const response = await fetch(
      `${editorEndpoints[routineEditorId].save}${editorPersonQuery()}`,
      {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify(normalizedEditorPayload()),
      },
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Kunne ikke gemme");
    routineEditorData = result;
    syncRoutineEditorPerson(result);
    routineEditorDraft = cloneRoutine(result.routines[routineEditorId]);
    routineEditorDirty = false;
    editorMessage(`Ændringerne for ${routineEditorPersonName} er gemt.`);
    if (typeof loadRoutines === "function") await loadRoutines();
    renderRoutineEditor();
  } catch (error) {
    editorMessage(error.message || "Kunne ikke gemme ændringerne.");
  } finally {
    editorSetPending(false);
  }
}

async function restoreRoutineDefault() {
  if (routineEditorPending || !editorRoutineIds.has(routineEditorId)) return;
  if (!window.confirm("Gendan standardrutinen? Dagens fremgang for denne rutine nulstilles.")) return;
  editorSetPending(true);
  try {
    const csrf = await editorCsrfToken();
    const response = await fetch(
      `${editorEndpoints[routineEditorId].reset}${editorPersonQuery()}`,
      {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRF-Token": csrf },
      },
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Kunne ikke gendanne standard");
    routineEditorData = result;
    routineEditorDraft = cloneRoutine(result.routines[routineEditorId]);
    routineEditorDirty = false;
    editorMessage(`Standardrutinen for ${routineEditorPersonName} er gendannet.`);
    if (typeof loadRoutines === "function") await loadRoutines();
    renderRoutineEditor();
  } catch (error) {
    editorMessage(error.message || "Kunne ikke gendanne standardrutinen.");
  } finally {
    editorSetPending(false);
  }
}

function initializeRoutineEditor() {
  const editButton = editorElement("routineEditButton");
  if (!editButton) return;
  editButton.addEventListener("click", openRoutineEditor);
  editorElement("routineEditorClose")?.addEventListener("click", closeRoutineEditor);
  editorElement("routineEditorCancel")?.addEventListener("click", closeRoutineEditor);
  editorElement("routineEditorForm")?.addEventListener("submit", saveRoutineEditor);
  editorElement("routineEditorRestore")?.addEventListener("click", restoreRoutineDefault);
  editorElement("routineEditorAdd")?.addEventListener("click", () => {
    routineEditorDraft.tasks.push({
      id: `draft_${Date.now()}`,
      title: "Nyt trin",
      pictogram: "play",
      time: null,
      weekdays: [],
    });
    markEditorDirty();
    renderRoutineEditor();
  });
  editorElement("routineEditorLabel")?.addEventListener("input", (event) => {
    routineEditorDraft.label = event.target.value;
    markEditorDirty();
  });
  document.querySelectorAll("[data-editor-routine]").forEach((button) => {
    button.addEventListener("click", () => switchEditorRoutine(button.dataset.editorRoutine));
  });
  window.addEventListener("beforeunload", (event) => {
    if (!routineEditorDirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
}

if (familyModuleEnabled("routines")) initializeRoutineEditor();
