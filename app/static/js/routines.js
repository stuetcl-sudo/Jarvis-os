const routineIds = new Set(["morning", "evening"]);
const routineEndpoints = {
  morning: {
    complete: "/api/family/routines/morning/complete",
    back: "/api/family/routines/morning/back",
    reset: "/api/family/routines/morning/reset",
  },
  evening: {
    complete: "/api/family/routines/evening/complete",
    back: "/api/family/routines/evening/back",
    reset: "/api/family/routines/evening/reset",
  },
};
const routinePictograms = new Set([
  "wake", "tv", "breakfast", "clothes", "teeth", "tablet", "outerwear", "school",
  "homework", "exercise", "play", "dinner", "cleanup", "bath", "laundry", "bed",
  "audio", "sleep", "complete",
]);

let routineState = null;
let activeRoutineId = null;
let activePersonId = null;
let routineCsrfToken = null;
let routineRequestPending = false;

function routineElement(id) {
  return document.getElementById(id);
}

function setRoutineText(id, value) {
  const element = routineElement(id);
  if (element) element.textContent = value;
}

function setRoutineStale(message) {
  const notice = routineElement("routineStaleNotice");
  if (!notice) return;
  notice.textContent = message;
  notice.hidden = !message;
}

function isWallDashboard() {
  return document.body.dataset.wallDashboard === "true";
}

function ensureRoutinePersonStyles() {
  if (document.querySelector('link[data-routine-person-styles="true"]')) return;
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/static/css/routine-person-switch.css?v=v0.18";
  link.dataset.routinePersonStyles = "true";
  document.head.append(link);
}

function syncRoutinePictogramButton() {
  const frame = document.querySelector(".routine-pictogram-frame");
  const completeButton = routineElement("routineComplete");
  if (!frame || !isWallDashboard()) return;

  const active = Boolean(completeButton && !completeButton.hidden && !completeButton.disabled && !routineRequestPending);
  frame.setAttribute("role", "button");
  frame.setAttribute("tabindex", active ? "0" : "-1");
  frame.setAttribute("aria-label", active ? "Færdiggør dette trin" : "Rutinepiktogram");
  frame.setAttribute("aria-disabled", String(!active));
}

function setRoutineBusy(busy) {
  routineRequestPending = busy;
  document.querySelectorAll("[data-routine-select], [data-routine-person], #routineBack, #routineComplete, #routineReset").forEach((button) => {
    button.disabled = busy;
  });
  syncRoutinePictogramButton();
}

function setRoutinePictogram(name, alternativeText) {
  const safeName = routinePictograms.has(name) ? name : "complete";
  const use = routineElement("routinePictogramUse");
  const pictogram = routineElement("routinePictogram");
  if (use) use.setAttribute("href", `/static/pictograms/routines.svg#${safeName}`);
  if (pictogram) pictogram.setAttribute("aria-label", alternativeText);
}

function routineFor(id) {
  if (!routineIds.has(id) || !routineState?.routines) return null;
  return routineState.routines[id] || null;
}

function renderRoutinePeople() {
  const content = document.querySelector(".routine-card-content");
  const panel = routineElement("routinePanel");
  if (!content || !panel) return;

  let selector = routineElement("routinePersonSwitch");
  if (!selector) {
    selector = document.createElement("div");
    selector.id = "routinePersonSwitch";
    selector.className = "routine-person-switch";
    selector.setAttribute("role", "group");
    selector.setAttribute("aria-label", "Vælg person");
    content.insertBefore(selector, panel);
  }

  const people = Array.isArray(routineState?.persons) ? routineState.persons : [];
  selector.replaceChildren();
  selector.hidden = people.length < 2;
  people.forEach((person) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.routinePerson = person.user_id;
    button.textContent = person.display_name || "Person";
    button.setAttribute("aria-pressed", String(person.user_id === activePersonId));
    button.disabled = routineRequestPending;
    button.addEventListener("click", async () => {
      if (routineRequestPending || person.user_id === activePersonId) return;
      activePersonId = person.user_id;
      setRoutineBusy(true);
      setRoutineText("routineMessage", "Skifter person…");
      try {
        await loadRoutines();
      } finally {
        setRoutineBusy(false);
      }
    });
    selector.append(button);
  });
}

function renderRoutine() {
  const card = document.querySelector('[data-family-card="routine"]');
  if (!card || !routineState || routineState.status !== "ok") {
    if (card) card.hidden = true;
    return;
  }
  if (!routineIds.has(activeRoutineId)) activeRoutineId = routineState.recommended;
  const routine = routineFor(activeRoutineId);
  if (!routine) {
    card.hidden = true;
    return;
  }

  card.hidden = false;
  setRoutineStale("");
  renderRoutinePeople();
  document.querySelectorAll("[data-routine-select]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.routineSelect === activeRoutineId));
  });
  setRoutineText("routineLabel", routine.label);
  setRoutineText("routineProgress", routine.completed
    ? `${routine.total} trin færdige`
    : `Trin ${routine.current_index + 1} af ${routine.total}`);

  const completeButton = routineElement("routineComplete");
  const backButton = routineElement("routineBack");
  const resetButton = routineElement("routineReset");
  const time = routineElement("routineTime");

  if (routine.completed) {
    setRoutineText("routineTitle", "Godt klaret!");
    setRoutineText("routineMessage", "Rutinen er færdig for i dag.");
    setRoutinePictogram("complete", "Godt klaret");
    if (time) time.hidden = true;
    if (completeButton) completeButton.hidden = true;
    if (backButton) backButton.hidden = false;
    if (resetButton) {
      resetButton.hidden = false;
      resetButton.textContent = "Start forfra";
    }
  } else {
    const task = routine.current_task;
    setRoutineText("routineTitle", task?.title || "Næste trin");
    setRoutineText("routineMessage", "");
    setRoutinePictogram(task?.pictogram || "complete", task?.title || "Rutinepiktogram");
    if (time) {
      time.textContent = task?.time ? `Forslag: kl. ${task.time}` : "";
      time.hidden = !task?.time;
    }
    if (completeButton) completeButton.hidden = false;
    if (backButton) backButton.hidden = false;
    if (resetButton) {
      resetButton.hidden = !(document.body.dataset.familyRole === "owner" || document.body.dataset.familyRole === "adult");
      resetButton.textContent = "Nulstil rutine";
    }
  }

  if (backButton) backButton.disabled = routineRequestPending || routine.current_index === 0;
  if (completeButton) completeButton.disabled = routineRequestPending;
  syncRoutinePictogramButton();
  const panel = routineElement("routinePanel");
  if (panel) {
    panel.classList.remove("routine-transition");
    requestAnimationFrame(() => panel.classList.add("routine-transition"));
  }
}

async function loadRoutineCsrfToken() {
  if (routineCsrfToken) return routineCsrfToken;
  const response = await fetch("/api/auth/me", { credentials: "same-origin" });
  if (!response.ok) throw new Error("Login kræves");
  const profile = await response.json();
  routineCsrfToken = profile.csrf_token || null;
  if (!routineCsrfToken) throw new Error("Sikkerhedstoken mangler");
  return routineCsrfToken;
}

async function loadRoutines() {
  const card = document.querySelector('[data-family-card="routine"]');
  if (document.body.dataset.familyRole === "anonymous") {
    if (card) card.hidden = true;
    return;
  }
  try {
    const query = activePersonId ? `?person_id=${encodeURIComponent(activePersonId)}` : "";
    const response = await fetch(`/api/family/routines${query}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error("Rutinen kunne ikke hentes");
    routineState = await response.json();
    activePersonId = routineState.selected_person_id || null;
    if (!activeRoutineId) activeRoutineId = routineState.recommended;
    renderRoutine();
  } catch (error) {
    if (routineState) {
      renderRoutine();
      setRoutineStale("Viser senest hentede rutine");
    } else if (card) {
      card.hidden = true;
    }
  }
}

async function changeRoutine(action) {
  if (routineRequestPending || !routineIds.has(activeRoutineId)) return;
  const routine = routineFor(activeRoutineId);
  if (!routine || !activePersonId) return;
  if (action === "reset" && (document.body.dataset.familyRole === "owner" || document.body.dataset.familyRole === "adult")) {
    if (!window.confirm("Vil du starte denne rutine forfra?")) return;
  }

  setRoutineBusy(true);
  setRoutineText("routineMessage", "Gemmer…");
  try {
    const csrfToken = await loadRoutineCsrfToken();
    const endpoint = routineEndpoints[activeRoutineId][action];
    const payload = { person_id: activePersonId };
    if (action !== "reset") payload.expected_index = routine.current_index;
    const response = await fetch(endpoint, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("Rutinen kunne ikke gemmes");
    routineState = await response.json();
    activePersonId = routineState.selected_person_id || activePersonId;
    renderRoutine();
  } catch (error) {
    setRoutineText("routineMessage", "Prøv igen om lidt.");
  } finally {
    setRoutineBusy(false);
    renderRoutine();
  }
}

function completeRoutineFromPictogram() {
  if (!isWallDashboard() || routineRequestPending) return;
  const completeButton = routineElement("routineComplete");
  if (!completeButton || completeButton.hidden || completeButton.disabled) return;
  completeButton.click();
}

function initializeRoutineControls() {
  ensureRoutinePersonStyles();
  document.querySelectorAll("[data-routine-select]").forEach((button) => {
    button.addEventListener("click", () => {
      const selected = button.dataset.routineSelect;
      if (!routineIds.has(selected) || routineRequestPending) return;
      activeRoutineId = selected;
      renderRoutine();
    });
  });
  routineElement("routineComplete")?.addEventListener("click", () => changeRoutine("complete"));
  routineElement("routineBack")?.addEventListener("click", () => changeRoutine("back"));
  routineElement("routineReset")?.addEventListener("click", () => changeRoutine("reset"));

  const pictogramFrame = document.querySelector(".routine-pictogram-frame");
  pictogramFrame?.addEventListener("click", completeRoutineFromPictogram);
  pictogramFrame?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    completeRoutineFromPictogram();
  });
}

initializeRoutineControls();
loadRoutines();
setInterval(loadRoutines, 30000);
