(() => {
  const dueDateFormatter = new Intl.DateTimeFormat("da-DK", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
  const dueTimeFormatter = new Intl.DateTimeFormat("da-DK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  function setTaskState(message) {
    const state = document.getElementById("familyTasksState");
    const data = document.getElementById("familyTasksData");
    if (state) {
      state.textContent = message;
      state.hidden = false;
    }
    if (data) data.hidden = true;
  }

  function dueText(value) {
    if (!value) return "";
    const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
    const parsed = new Date(dateOnly ? `${value}T12:00:00` : value);
    if (Number.isNaN(parsed.getTime())) return "";
    const date = dueDateFormatter.format(parsed);
    return dateOnly ? `Senest ${date}` : `Senest ${date} kl. ${dueTimeFormatter.format(parsed)}`;
  }

  function createTaskItem(item) {
    const row = document.createElement("li");
    row.className = "family-task-item";

    const marker = document.createElement("span");
    marker.className = "family-task-marker";
    marker.setAttribute("aria-hidden", "true");

    const copy = document.createElement("div");
    const summary = document.createElement("p");
    summary.className = "family-task-summary";
    summary.textContent = item.summary || "Opgave";
    copy.append(summary);

    const due = dueText(item.due);
    if (due) {
      const deadline = document.createElement("p");
      deadline.className = "family-task-due";
      deadline.textContent = due;
      copy.append(deadline);
    }

    if (item.description) {
      const description = document.createElement("p");
      description.className = "family-task-description";
      description.textContent = item.description;
      copy.append(description);
    }

    row.append(marker, copy);
    return row;
  }

  function createTaskList(taskList) {
    const section = document.createElement("section");
    section.className = "family-task-list";

    const heading = document.createElement("div");
    heading.className = "family-task-list-heading";
    const title = document.createElement("h3");
    title.textContent = taskList.label || "Opgaver";
    const count = document.createElement("span");
    const total = Array.isArray(taskList.items) ? taskList.items.length : 0;
    count.textContent = `${total} ${total === 1 ? "punkt" : "punkter"}`;
    heading.append(title, count);

    const items = document.createElement("ol");
    items.className = "family-task-items";
    if (total === 0) {
      const empty = document.createElement("li");
      empty.className = "family-task-empty";
      empty.textContent = "Ingen åbne punkter";
      items.append(empty);
    } else {
      taskList.items.forEach((item) => items.append(createTaskItem(item)));
    }

    section.append(heading, items);
    return section;
  }

  function renderFamilyTasks(tasks) {
    if (tasks.status === "authentication_required") {
      setTaskState("Log ind for at se opgaver og lektier");
      return;
    }
    if (tasks.status === "not_configured") {
      setTaskState("Opgaver og lektier er ikke tilsluttet endnu");
      return;
    }
    if (tasks.status === "unavailable") {
      setTaskState("Opgaver og lektier kan ikke hentes lige nu");
      return;
    }

    const state = document.getElementById("familyTasksState");
    const data = document.getElementById("familyTasksData");
    if (state) state.hidden = true;
    if (data) data.hidden = false;

    const lists = document.getElementById("familyTaskLists");
    if (lists) {
      lists.replaceChildren();
      (tasks.lists || []).forEach((taskList) => lists.append(createTaskList(taskList)));
    }

    const notice = document.getElementById("familyTasksNotice");
    if (notice) {
      const messages = {
        partial: "En af listerne kunne ikke hentes",
        stale: "Viser senest hentede opgaver og lektier",
      };
      notice.textContent = messages[tasks.status] || "";
      notice.hidden = !messages[tasks.status];
    }
  }

  async function refreshFamilyTasks() {
    try {
      const response = await fetch("/api/family/tasks", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Opgaver kunne ikke hentes");
      renderFamilyTasks(await response.json());
    } catch (error) {
      setTaskState("Opgaver og lektier kan ikke hentes lige nu");
    }
  }

  refreshFamilyTasks();
  setInterval(refreshFamilyTasks, 30000);
})();
