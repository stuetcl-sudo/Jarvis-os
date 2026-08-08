(() => {
  const roleOptions = [
    ["adult", "Voksen"],
    ["child", "Barn"],
    ["wall_display", "Vægskærm"],
  ];
  const colorOptions = [
    ["blue", "Blå"], ["green", "Grøn"], ["violet", "Violet"],
    ["orange", "Orange"], ["pink", "Rosa"], ["teal", "Turkis"],
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
    card.dataset.userColor = user.display_color;
    card.append(
      element("strong", "", user.display_name),
      element("span", "", user.username),
      element("small", "", `${roleLabel(user.role)} · ${user.disabled ? "Deaktiveret" : "Aktiv"}`),
    );
    const profile = element("div", "classification-controls");
    const color = document.createElement("select");
    color.setAttribute("aria-label", `Farve for ${user.display_name}`);
    colorOptions.forEach(([value, label]) => {
      const option = element("option", "", label);
      option.value = value;
      option.selected = value === user.display_color;
      color.append(option);
    });
    const visibleLabel = element("label", "checkbox-control", "Vis på familie-/vægskærm");
    const visible = document.createElement("input");
    visible.type = "checkbox";
    visible.checked = Boolean(user.family_visible);
    visible.disabled = user.role === "wall_display";
    visibleLabel.prepend(visible);
    const saveProfile = element("button", "secondary", "Gem profil");
    saveProfile.type = "button";
    saveProfile.addEventListener("click", async () => {
      try {
        await getJson(`/api/admin/users/${encodeURIComponent(user.user_id)}/profile`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ display_color: color.value, family_visible: visible.checked }),
        });
        showNotice("Brugerprofilen er gemt.", "success");
        await loadUsers();
      } catch (error) {
        showNotice(error.message || "Brugerprofilen kunne ikke gemmes.", "error", 0);
      }
    });
    profile.append(color, visibleLabel, saveProfile);
    card.append(profile);

    if (user.role !== "owner") {
      const password = input("password", "password", "new-password");
      password.minLength = 12;
      password.maxLength = 128;
      password.placeholder = "Ny adgangskode";
      const reset = element("button", "secondary", "Skift adgangskode");
      reset.type = "button";
      reset.addEventListener("click", async () => {
        try {
          await getJson(`/api/admin/users/${encodeURIComponent(user.user_id)}/password`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: password.value }),
          });
          password.value = "";
          showNotice("Adgangskoden er ændret. Brugeren skal logge ind igen.", "success");
        } catch (error) {
          showNotice(error.message || "Adgangskoden kunne ikke ændres.", "error", 0);
        }
      });
      const remove = element("button", "danger", "Slet bruger");
      remove.type = "button";
      remove.addEventListener("click", async () => {
        if (!window.confirm(`Vil du slette ${user.display_name}? Handlingen kan ikke fortrydes.`)) return;
        try {
          await getJson(`/api/admin/users/${encodeURIComponent(user.user_id)}`, { method: "DELETE" });
          showNotice("Brugeren er slettet.", "success");
          await loadUsers();
          if (window.loadAdminScreens) await window.loadAdminScreens();
        } catch (error) {
          showNotice(error.message || "Brugeren kunne ikke slettes.", "error", 0);
        }
      });
      const actions = element("div", "quick-buttons");
      actions.append(password, reset, remove);
      card.append(actions);
    }
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
