(() => {
  const roleOptions = [
    ["adult", "Voksen"],
    ["child", "Barn"],
    ["wall_display", "Vægskærm"],
  ];

  function labeledInput(labelText, input) {
    const label = element("label", "screen-field", labelText);
    label.append(input);
    return label;
  }

  function input(type, name, autocomplete) {
    const control = document.createElement("input");
    control.type = type;
    control.name = name;
    control.required = true;
    control.autocomplete = autocomplete;
    return control;
  }

  function userCard(user) {
    const card = element("article", "module-card");
    card.append(
      element("strong", "", user.display_name),
      element("span", "", user.username),
      element("small", "", `${roleLabel(user.role)} · ${user.disabled ? "Deaktiveret" : "Aktiv"}`),
    );
    return card;
  }

  async function loadUsers() {
    const list = document.getElementById("adminUserList");
    if (!list) return;
    try {
      const data = await getJson("/api/admin/users");
      replaceContent(list, (data.users || []).map(userCard));
    } catch (error) {
      replaceContent(list, [emptyState(`Brugere kunne ikke hentes: ${error.message}`)]);
    }
  }

  async function createUser(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = {};
    new FormData(form).forEach((value, key) => { payload[key] = value; });
    try {
      await getJson("/api/admin/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      form.reset();
      showNotice("Brugeren er oprettet.", "success");
      await loadUsers();
      if (window.loadAdminScreens) await window.loadAdminScreens();
    } catch (error) {
      showNotice(error.message || "Brugeren kunne ikke oprettes.", "error", 0);
    }
  }

  function initializeUsers() {
    const target = document.getElementById("section-users");
    if (!target || document.getElementById("adminUserPanel")) return;
    const panel = element("section", "panel");
    panel.id = "adminUserPanel";
    panel.append(element("h3", "", "Opret lokal bruger"));
    panel.append(element("p", "panel-help", "Opret en voksen, et barn eller en konto til en vægskærm."));

    const form = element("form", "screen-form");
    form.id = "adminUserForm";
    const grid = element("div", "content-grid two-columns");
    const displayName = input("text", "display_name", "name");
    const username = input("text", "username", "username");
    const password = input("password", "password", "new-password");
    password.minLength = 12;
    password.maxLength = 128;
    const role = document.createElement("select");
    role.name = "role";
    role.required = true;
    roleOptions.forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      role.append(option);
    });
    grid.append(
      labeledInput("Navn", displayName),
      labeledInput("Brugernavn", username),
      labeledInput("Rolle", role),
      labeledInput("Adgangskode (12–128 tegn)", password),
    );
    const save = element("button", "", "Opret bruger");
    save.type = "submit";
    form.append(grid, save);
    form.addEventListener("submit", createUser);

    const list = element("div", "module-grid");
    list.id = "adminUserList";
    panel.append(form, element("h3", "", "Lokale brugere"), list);
    target.append(panel);
    loadUsers();
  }

  initializeUsers();
})();
