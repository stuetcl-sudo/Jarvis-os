(() => {
  const screenTypes = [
    ["wall-large", "Stor vægskærm"],
    ["wall-tablet", "Tablet / køkken"],
    ["wall-square", "Kvadratisk skærm"],
    ["mobile", "Mobil"],
  ];
  const modules = [
    ["routine", "Rutine"],
    ["calendar", "Kalender"],
    ["weather", "Vejr / UV"],
    ["meal", "Madplan"],
    ["tasks", "Opgaver"],
    ["home", "Hjem"],
    ["system", "Systemstatus"],
  ];
  const defaultModules = ["routine", "calendar", "weather", "meal", "tasks", "home"];
  let selectedScreen = null;

  function moduleLabels(values) {
    const lookup = Object.fromEntries(modules);
    return (values || []).map((key) => lookup[key] || key).join(", ") || "Ingen moduler";
  }

  function slugFromName(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/æ/g, "ae")
      .replace(/ø/g, "oe")
      .replace(/å/g, "aa")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40);
  }

  function selectedModules() {
    return Array.from(document.querySelectorAll("[data-screen-module]:checked")).map((input) => input.value);
  }

  function labeledInput(labelText, input) {
    const label = element("label", "screen-field", labelText);
    label.append(input);
    return label;
  }

  function textInput(id, placeholder, maxLength = 80) {
    const input = document.createElement("input");
    input.id = id;
    input.maxLength = maxLength;
    input.placeholder = placeholder;
    return input;
  }

  function fillForm(screen = null) {
    selectedScreen = screen;
    const name = document.getElementById("screenName");
    const slug = document.getElementById("screenSlug");
    const type = document.getElementById("screenType");
    const active = document.getElementById("screenActive");
    if (!name || !slug || !type || !active) return;
    name.value = screen?.name || "";
    slug.value = screen?.slug || "";
    slug.disabled = screen?.slug === "wall";
    type.value = screen?.screen_type || "wall-large";
    active.checked = screen?.is_active !== false;
    const activeModules = screen?.modules || defaultModules;
    document.querySelectorAll("[data-screen-module]").forEach((input) => {
      input.checked = activeModules.includes(input.value);
    });
    document.getElementById("screenFormTitle").textContent = screen ? `Rediger ${screen.name}` : "Opret ny skærm";
    document.getElementById("screenSaveButton").textContent = screen ? "Gem skærm" : "Opret skærm";
  }

  function screenCard(screen) {
    const card = element("article", "module-card screen-card");
    const title = element("strong", "", screen.name);
    const url = element("span", "", screen.url);
    const detail = element("small", "", `${screenTypes.find(([key]) => key === screen.screen_type)?.[1] || screen.screen_type} · ${moduleLabels(screen.modules)}`);
    const actions = element("div", "quick-buttons");

    const open = element("a", "family-link", "Åbn");
    open.href = screen.url;
    open.target = "_blank";
    open.rel = "noreferrer";

    const edit = element("button", "secondary", "Rediger");
    edit.type = "button";
    edit.addEventListener("click", () => fillForm(screen));

    actions.append(open, edit);
    if (screen.slug !== "wall") {
      const remove = element("button", "danger", "Slet");
      remove.type = "button";
      remove.addEventListener("click", () => deleteScreen(screen));
      actions.append(remove);
    }
    card.append(title, url, detail, actions);
    return card;
  }

  async function loadScreens() {
    const list = document.getElementById("screenList");
    if (!list) return;
    try {
      const data = await getJson("/api/admin/screens");
      replaceContent(list, (data.screens || []).map(screenCard));
    } catch (error) {
      replaceContent(list, [emptyState(`Skærme kunne ikke hentes: ${error.message}`)]);
    }
  }

  async function saveScreen(event) {
    event.preventDefault();
    const name = document.getElementById("screenName").value.trim();
    const rawSlug = document.getElementById("screenSlug").value.trim() || slugFromName(name);
    const payload = {
      name,
      slug: selectedScreen?.slug === "wall" ? "wall" : rawSlug,
      screen_type: document.getElementById("screenType").value,
      modules: selectedModules(),
      is_active: document.getElementById("screenActive").checked,
    };
    try {
      await getJson("/api/admin/screens", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      showNotice("Skærmen er gemt.", "success");
      fillForm(null);
      await loadScreens();
    } catch (error) {
      showNotice(`Skærmen kunne ikke gemmes: ${error.message}`, "error", 0);
    }
  }

  async function deleteScreen(screen) {
    if (!window.confirm(`Slet skærmen “${screen.name}”? Linket ${screen.url} stopper med at virke.`)) return;
    try {
      await getJson(`/api/admin/screens/${encodeURIComponent(screen.slug)}`, { method: "DELETE" });
      showNotice("Skærmen er slettet.", "success");
      if (selectedScreen?.slug === screen.slug) fillForm(null);
      await loadScreens();
    } catch (error) {
      showNotice(`Skærmen kunne ikke slettes: ${error.message}`, "error", 0);
    }
  }

  function createTypeSelect() {
    const select = document.createElement("select");
    select.id = "screenType";
    screenTypes.forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      select.append(option);
    });
    return select;
  }

  function createActiveControl() {
    const label = element("label", "checkbox-control", "");
    const input = document.createElement("input");
    input.id = "screenActive";
    input.type = "checkbox";
    input.checked = true;
    label.append(input, document.createTextNode(" Aktiv"));
    return label;
  }

  function createModulePicker() {
    const fieldset = element("fieldset", "screen-module-picker");
    fieldset.append(element("legend", "", "Moduler"));
    modules.forEach(([value, labelText]) => {
      const label = element("label", "checkbox-control", "");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = value;
      input.dataset.screenModule = "true";
      label.append(input, document.createTextNode(` ${labelText}`));
      fieldset.append(label);
    });
    return fieldset;
  }

  function createScreenForm() {
    const form = element("form", "screen-form");
    form.id = "screenForm";
    form.append(element("h4", "", "Opret ny skærm"));
    form.firstChild.id = "screenFormTitle";

    const grid = element("div", "content-grid two-columns");
    const name = textInput("screenName", "Stuen");
    name.required = true;
    const slug = textInput("screenSlug", "stuen", 40);
    grid.append(
      labeledInput("Navn", name),
      labeledInput("Slug / link", slug),
      labeledInput("Type", createTypeSelect()),
      createActiveControl(),
    );

    const actions = element("div", "quick-buttons");
    const save = element("button", "", "Opret skærm");
    save.id = "screenSaveButton";
    save.type = "submit";
    actions.append(save);

    form.append(grid, createModulePicker(), actions);
    form.addEventListener("submit", saveScreen);
    name.addEventListener("input", (event) => {
      if (!selectedScreen && !slug.value) slug.value = slugFromName(event.target.value);
    });
    return form;
  }

  function createScreensPanel() {
    const target = document.getElementById("section-modules");
    if (!target || document.getElementById("screenAdminPanel")) return;
    const panel = element("section", "panel screen-admin-panel");
    panel.id = "screenAdminPanel";
    const heading = element("div", "panel-head");
    const text = document.createElement("div");
    text.append(
      element("h3", "", "Skærme"),
      element("p", "panel-help", "Opret faste links til stue, køkken, børneskærm eller andre vægvisninger."),
    );
    const reset = element("button", "secondary", "Ny skærm");
    reset.type = "button";
    reset.addEventListener("click", () => fillForm(null));
    heading.append(text, reset);

    const list = element("div", "module-grid screen-list");
    list.id = "screenList";
    panel.append(heading, createScreenForm(), list);
    target.append(panel);
    fillForm(null);
    loadScreens();
  }

  createScreensPanel();
  window.loadAdminScreens = loadScreens;
})();
