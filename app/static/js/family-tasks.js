(() => {
  if (!familyModuleEnabled("tasks")) return;
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
  const WALL_SHOPPING_PREVIEW_LIMIT = 5;
  const pendingTasks = new Set();
  let taskCsrfToken = null;
  let activeTaskAssigneeId = null;
  let latestFamilyTasks = null;

  function setTaskState(message) {
    const state = document.getElementById("familyTasksState");
    const data = document.getElementById("familyTasksData");
    if (state) {
      state.textContent = message;
      state.hidden = false;
    }
    if (data) data.hidden = true;
  }

  function showTaskRefreshFailure() {
    const state = document.getElementById("familyTasksState");
    const data = document.getElementById("familyTasksData");

    if (data && !data.hidden) {
      if (state) state.hidden = true;
      setTaskNotice("Viser senest hentede familielister");
      return;
    }

    setTaskState("Familiens lister kan ikke hentes lige nu");
  }

  function setTaskNotice(message) {
    const notice = document.getElementById("familyTasksNotice");
    if (!notice) return;
    notice.textContent = message;
    notice.hidden = !message;
  }

  function dueText(value) {
    if (!value) return "";
    const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(value);
    const parsed = new Date(dateOnly ? `${value}T12:00:00` : value);
    if (Number.isNaN(parsed.getTime())) return "";
    const date = dueDateFormatter.format(parsed);
    return dateOnly ? `Senest ${date}` : `Senest ${date} kl. ${dueTimeFormatter.format(parsed)}`;
  }

  async function loadTaskCsrfToken() {
    if (taskCsrfToken) return taskCsrfToken;
    const response = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (!response.ok) throw new Error("Login kræves");
    const profile = await response.json();
    taskCsrfToken = profile.csrf_token || null;
    if (!taskCsrfToken) throw new Error("Sikkerhedstoken mangler");
    return taskCsrfToken;
  }

  async function taskWrite(listKey, method, suffix, payload, message) {
    const csrfToken = await loadTaskCsrfToken();
    setTaskNotice(message);
    const response = await fetch(`/api/family/tasks/${encodeURIComponent(listKey)}/${suffix}`, {
      method,
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error("Ændringen kunne ikke gemmes");
    renderFamilyTasks(await response.json());
  }

  async function completeFamilyTask(listKey, item, button) {
    const uid = String(item?.uid || "").trim();
    const safeListKey = String(listKey || "").trim();
    if (!uid || !safeListKey) return;
    const pendingKey = `${safeListKey}\u0000${uid}`;
    if (pendingTasks.has(pendingKey)) return;

    pendingTasks.add(pendingKey);
    button.disabled = true;
    button.classList.add("is-saving");
    button.setAttribute("aria-busy", "true");

    try {
      await taskWrite(safeListKey, "POST", "complete", { item: uid }, "Markerer som færdig…");
    } catch (error) {
      setTaskNotice("Kunne ikke markere punktet som færdigt. Prøv igen.");
    } finally {
      pendingTasks.delete(pendingKey);
      if (button.isConnected) {
        button.disabled = false;
        button.classList.remove("is-saving");
        button.removeAttribute("aria-busy");
      }
    }
  }

  async function editFamilyTask(listKey, item) {
    const summary = window.prompt("Ret punktet", item.summary || "");
    if (summary === null) return;
    const cleaned = summary.trim();
    if (!cleaned) {
      setTaskNotice("Punktet skal have en titel.");
      return;
    }
    try {
      await taskWrite(listKey, "PUT", "items", {
        item: item.uid,
        summary: cleaned,
        description: item.description || null,
      }, "Gemmer ændringen…");
    } catch (error) {
      setTaskNotice("Kunne ikke gemme ændringen. Prøv igen.");
    }
  }

  async function removeFamilyTask(listKey, item) {
    if (!window.confirm(`Fjern “${item.summary || "punktet"}”?`)) return;
    try {
      await taskWrite(listKey, "DELETE", "items", { item: item.uid }, "Fjerner punktet…");
    } catch (error) {
      setTaskNotice("Kunne ikke fjerne punktet. Prøv igen.");
    }
  }

  async function assignFamilyTask(listKey, item, assigneeId, select) {
    const uid = String(item?.uid || "").trim();
    const safeListKey = String(listKey || "").trim();
    if (!uid || !safeListKey) return;

    const previousAssigneeId = normalizedAssigneeId(item.assignee_id);
    select.disabled = true;
    select.setAttribute("aria-busy", "true");

    try {
      await taskWrite(
        safeListKey,
        "PUT",
        "assignment",
        {
          item: uid,
          assignee_id: normalizedAssigneeId(assigneeId),
        },
        "Gemmer tildelingen…",
      );
    } catch (error) {
      select.value = previousAssigneeId || "";
      setTaskNotice("Kunne ikke gemme tildelingen. Prøv igen.");
    } finally {
      if (select.isConnected) {
        select.disabled = false;
        select.removeAttribute("aria-busy");
      }
    }
  }

  function createTaskAssigneeSelect(item, listKey, people) {
    const label = document.createElement("label");
    const labelText = document.createElement("span");
    const select = document.createElement("select");

    label.className = "family-task-assignee";
    labelText.textContent = "Tildel til";
    select.setAttribute(
      "aria-label",
      `Tildel ${item.summary || "opgaven"} til`,
    );

    people.forEach((person) => {
      const option = document.createElement("option");
      const personId = normalizedAssigneeId(person.user_id);

      option.value = personId || "";
      option.textContent = taskPersonLabel(person);
      option.selected =
        personId === normalizedAssigneeId(item.assignee_id);

      select.append(option);
    });

    select.addEventListener("change", () => {
      assignFamilyTask(listKey, item, select.value, select);
    });

    label.append(labelText, select);
    return label;
  }

  function createTaskActions(item, listKey, permissions, people) {
    const actions = document.createElement("div");
    actions.className = "family-task-actions";
    if (!permissions.canEdit && !permissions.canRemove) return actions;

    if (permissions.canEdit && people.length > 0) {
      actions.append(createTaskAssigneeSelect(item, listKey, people));
    }

    if (permissions.canEdit) {
      const edit = document.createElement("button");
      edit.type = "button";
      edit.textContent = "Ret";
      edit.addEventListener("click", () => editFamilyTask(listKey, item));
      actions.append(edit);
    }

    if (permissions.canRemove) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "danger";
      remove.textContent = "Fjern";
      remove.addEventListener("click", () => removeFamilyTask(listKey, item));
      actions.append(remove);
    }

    return actions;
  }

  function createTaskItem(item, listKey, permissions, people) {
    const row = document.createElement("li");
    row.className = "family-task-item";

    const complete = document.createElement("button");
    complete.type = "button";
    complete.className = "family-task-complete";
    complete.disabled = !permissions.canComplete;
    complete.setAttribute("aria-label", `Markér ${item.summary || "opgaven"} som færdig`);
    if (permissions.canComplete) complete.addEventListener("click", () => completeFamilyTask(listKey, item, complete));

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
    copy.append(createTaskActions(item, listKey, permissions, people));
    row.append(complete, copy);
    return row;
  }

  function createAddForm(taskList) {
    const form = document.createElement("form");
    form.className = "family-task-add";
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 160;
    input.required = true;
    input.placeholder = isShoppingList(taskList) ? "Tilføj en vare" : "Tilføj et punkt";
    input.setAttribute("aria-label", `Tilføj til ${taskList.label || "listen"}`);
    const button = document.createElement("button");
    button.type = "submit";
    button.textContent = "Tilføj";
    form.append(input, button);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const summary = input.value.trim();
      if (!summary) return;
      input.disabled = true;
      button.disabled = true;
      try {
        await taskWrite(taskList.key, "POST", "items", { summary, description: null }, "Tilføjer punktet…");
      } catch (error) {
        setTaskNotice("Kunne ikke tilføje punktet. Prøv igen.");
        input.disabled = false;
        button.disabled = false;
        input.focus();
      }
    });
    return form;
  }

  function isShoppingList(taskList) {
    const key = String(taskList?.key || "").toLowerCase();
    const label = String(taskList?.label || "").toLowerCase();
    return key.includes("shopping") || key.includes("indkob") || key.includes("indkøb") || label.includes("shopping") || label.includes("indkøb");
  }

  function isWallDisplay() {
    return document.body.dataset.familyRole === "wall_display" || document.body.dataset.wallDashboard === "true";
  }

  function visibleTaskItems(taskList) {
    const items = Array.isArray(taskList.items) ? taskList.items : [];
    return isWallDisplay() && isShoppingList(taskList)
      ? items.slice(0, WALL_SHOPPING_PREVIEW_LIMIT)
      : items;
  }

  function taskCountText(taskList, visibleCount, total) {
    if (isWallDisplay() && isShoppingList(taskList) && total > visibleCount) {
      return `${visibleCount} af ${total} punkter`;
    }
    return `${total} ${total === 1 ? "punkt" : "punkter"}`;
  }

  function normalizedAssigneeId(value) {
    const identifier = String(value || "").trim();
    return identifier || null;
  }

  function taskPersonLabel(person) {
    return person?.display_name || "Familien";
  }

  function normalizedPersonName(value) {
    return String(value || "")
      .trim()
      .toLocaleLowerCase("da-DK")
      .replace(/familien/g, "familie");
  }

  function taskPersonCalendarColor(person) {
    const personName = normalizedPersonName(taskPersonLabel(person));
    const calendars =
      typeof latestCalendarSnapshot !== "undefined" &&
      Array.isArray(latestCalendarSnapshot?.calendars)
        ? latestCalendarSnapshot.calendars
        : [];

    const calendar = calendars.find((item) => {
      const label =
        item?.label ||
        item?.name ||
        item?.summary ||
        item?.title ||
        "";
      return normalizedPersonName(label) === personName;
    });

    const color = String(calendar?.color || "").trim().toLowerCase();
    if (["green", "blue", "violet", "yellow"].includes(color)) {
      return color;
    }

    const fallbackColors = {
      emma: "green",
      liam: "blue",
      dennis: "violet",
      familie: "yellow",
    };
    return fallbackColors[personName] || "";
  }


  function selectedTaskPerson(tasks) {
    const people = Array.isArray(tasks?.people) ? tasks.people : [];
    return people.find(
      (person) => normalizedAssigneeId(person.user_id) === activeTaskAssigneeId,
    ) || people[0] || {
      user_id: null,
      display_name: "Familien",
      count: 0,
    };
  }

  function syncActiveTaskPerson(tasks) {
    const people = Array.isArray(tasks?.people) ? tasks.people : [];
    const selectionExists = people.some(
      (person) => normalizedAssigneeId(person.user_id) === activeTaskAssigneeId,
    );

    if (!selectionExists) {
      activeTaskAssigneeId = normalizedAssigneeId(people[0]?.user_id);
    }
  }

  function renderTaskPersonSwitch(tasks) {
    const container = document.getElementById("familyTaskPersonSwitch");
    if (!container) return;

    const people = Array.isArray(tasks?.people) ? tasks.people : [];
    syncActiveTaskPerson(tasks);
    container.replaceChildren();

    people.forEach((person) => {
      const personId = normalizedAssigneeId(person.user_id);
      const selected = personId === activeTaskAssigneeId;
      const button = document.createElement("button");
      const name = document.createElement("span");
      const count = document.createElement("strong");

      button.type = "button";
      button.className = "family-task-person-button";
      const calendarColor = taskPersonCalendarColor(person);
      if (calendarColor) button.dataset.calendarColor = calendarColor;
      button.setAttribute("aria-pressed", selected ? "true" : "false");
      button.setAttribute(
        "aria-label",
        `${taskPersonLabel(person)}, ${Number(person.count) || 0} åbne opgaver`,
      );

      name.textContent = taskPersonLabel(person);
      count.textContent = String(Number(person.count) || 0);

      button.append(name, count);
      button.addEventListener("click", () => {
        activeTaskAssigneeId = personId;
        if (latestFamilyTasks) renderFamilyTasks(latestFamilyTasks);
      });
      container.append(button);
    });

    container.hidden = people.length === 0;
  }

  function filteredTaskLists(tasks) {
    const lists = Array.isArray(tasks?.lists) ? tasks.lists : [];

    return lists.map((taskList) => ({
      ...taskList,
      items: (Array.isArray(taskList.items) ? taskList.items : []).filter(
        (item) => normalizedAssigneeId(item.assignee_id) === activeTaskAssigneeId,
      ),
    }));
  }

  function createTaskFilterEmpty(tasks) {
    const empty = document.createElement("p");
    const person = selectedTaskPerson(tasks);

    empty.className = "family-task-filter-empty";
    empty.textContent = `${taskPersonLabel(person)} har ingen åbne opgaver`;
    return empty;
  }

  function taskPermissions(tasks) {
    return {
      canAdd: Boolean(tasks.can_add),
      canComplete: Boolean(tasks.can_complete),
      canEdit: Boolean(tasks.can_edit),
      canRemove: Boolean(tasks.can_remove),
    };
  }

  function createTaskList(taskList, permissions, allowAdd, people) {
    const section = document.createElement("section");
    section.className = `family-task-list family-task-list-${taskList.key || "general"}`;
    if (isShoppingList(taskList)) section.classList.add("family-task-list-shopping-list");

    const allItems = Array.isArray(taskList.items) ? taskList.items : [];
    const visibleItems = visibleTaskItems(taskList);
    const heading = document.createElement("div");
    heading.className = "family-task-list-heading";
    const title = document.createElement("h3");
    title.textContent = taskList.label || "Opgaver";
    const count = document.createElement("span");
    const total = allItems.length;
    count.textContent = taskCountText(taskList, visibleItems.length, total);
    heading.append(title, count);

    const items = document.createElement("ol");
    items.className = "family-task-items";
    if (total === 0) {
      const empty = document.createElement("li");
      empty.className = "family-task-empty";
      empty.textContent = "Ingen åbne punkter";
      items.append(empty);
    } else {
      visibleItems.forEach((item) => {
        items.append(createTaskItem(item, taskList.key, permissions, people));
      });
      if (visibleItems.length < total) {
        const more = document.createElement("li");
        more.className = "family-task-more";
        more.textContent = `${total - visibleItems.length} mere på listen`;
        items.append(more);
      }
    }

    section.append(heading);
    if (permissions.canAdd && allowAdd) section.append(createAddForm(taskList));
    section.append(items);
    return section;
  }

  function renderFamilyTasks(tasks) {
    latestFamilyTasks = tasks;

    if (tasks.status === "authentication_required") {
      setTaskState("Log ind for at se familiens lister");
      return;
    }
    if (tasks.status === "not_configured") {
      setTaskState("Familiens lister er ikke tilsluttet endnu");
      return;
    }
    if (tasks.status === "unavailable") {
      showTaskRefreshFailure();
      return;
    }

    const state = document.getElementById("familyTasksState");
    const data = document.getElementById("familyTasksData");
    if (state) state.hidden = true;
    if (data) data.hidden = false;

    const permissions = taskPermissions(tasks);
    const people = Array.isArray(tasks.people) ? tasks.people : [];
    const lists = document.getElementById("familyTaskLists");
    renderTaskPersonSwitch(tasks);

    if (lists) {
      lists.replaceChildren();

      const filteredLists = filteredTaskLists(tasks);
      const visibleTotal = filteredLists.reduce(
        (total, taskList) => total + taskList.items.length,
        0,
      );
      const familySelected = activeTaskAssigneeId === null;

      if (visibleTotal === 0 && !familySelected) {
        lists.append(createTaskFilterEmpty(tasks));
      } else {
        filteredLists.forEach((taskList) => {
          if (familySelected || taskList.items.length > 0) {
            lists.append(
              createTaskList(
                taskList,
                permissions,
                familySelected,
                people,
              ),
            );
          }
        });
      }
    }

    const messages = {
      partial: "En af listerne kunne ikke hentes",
      stale: "Viser senest hentede familielister",
    };
    setTaskNotice(messages[tasks.status] || "");
  }

  async function refreshFamilyTasks() {
    try {
      const response = await fetch("/api/family/tasks", { credentials: "same-origin" });
      if (!response.ok) throw new Error("Familiens lister kunne ikke hentes");
      renderFamilyTasks(await response.json());
    } catch (error) {
      showTaskRefreshFailure();
    }
  }

  window.addEventListener("jarvis:calendar-updated", () => {
    if (latestFamilyTasks) renderFamilyTasks(latestFamilyTasks);
  });

  refreshFamilyTasks();
  setInterval(refreshFamilyTasks, 30000);
})();
