(() => {
  const roleOrder = ["owner", "adult", "child", "wall_display"];
  const featureOrder = ["calendar", "weather", "meal", "tasks", "safety"];
  const featureLabels = {
    calendar: "Kalender",
    weather: "Vejr",
    meal: "Madplan",
    tasks: "Opgaver",
    safety: "Tryghedsstatus",
  };
  let visibilityRules = null;

  function featureLabel(feature) {
    return featureLabels[feature] || feature;
  }

  function createRoleColumn(role) {
    const card = element("article", "module-card role-visibility-card");
    card.append(element("strong", "", roleLabel(role)));
    if (role === "owner") {
      card.append(element("small", "", "Ejer ser altid alt."));
    }
    featureOrder.forEach((feature) => {
      const label = element("label", "checkbox-control", "");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.visibilityRole = role;
      input.dataset.visibilityFeature = feature;
      input.checked = visibilityRules?.[role]?.[feature] !== false;
      input.disabled = role === "owner";
      label.append(input, document.createTextNode(` ${featureLabel(feature)}`));
      card.append(label);
    });
    return card;
  }

  function collectVisibilityRules() {
    const rules = {};
    roleOrder.forEach((role) => {
      rules[role] = {};
      featureOrder.forEach((feature) => {
        const input = document.querySelector(`[data-visibility-role="${role}"][data-visibility-feature="${feature}"]`);
        rules[role][feature] = input ? input.checked : true;
      });
    });
    return rules;
  }

  function renderVisibilityPanel() {
    const grid = document.getElementById("roleVisibilityGrid");
    if (!grid || !visibilityRules) return;
    replaceContent(grid, roleOrder.map(createRoleColumn));
  }

  async function loadRoleVisibility() {
    const status = document.getElementById("roleVisibilityStatus");
    try {
      const data = await getJson("/api/admin/family-visibility");
      visibilityRules = data.rules || {};
      renderVisibilityPanel();
      if (status) status.textContent = "";
    } catch (error) {
      if (status) status.textContent = `Synlighed kunne ikke hentes: ${error.message}`;
    }
  }

  async function saveRoleVisibility() {
    const status = document.getElementById("roleVisibilityStatus");
    try {
      await getJson("/api/admin/family-visibility", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rules: collectVisibilityRules() }),
      });
      showNotice("Synlighed er gemt.", "success");
      if (status) status.textContent = "Gemt.";
      await loadRoleVisibility();
    } catch (error) {
      if (status) status.textContent = `Synlighed kunne ikke gemmes: ${error.message}`;
      showNotice(`Synlighed kunne ikke gemmes: ${error.message}`, "error", 0);
    }
  }

  function createRoleVisibilityPanel() {
    const target = document.getElementById("section-users");
    if (!target || document.getElementById("roleVisibilityPanel")) return;
    const panel = element("section", "panel role-visibility-panel");
    panel.id = "roleVisibilityPanel";
    const heading = element("div", "panel-head");
    const text = document.createElement("div");
    text.append(
      element("h3", "", "Hvem må se hvad?"),
      element("p", "panel-help", "Vælg hvilke dele af familievisningen hver rolle må se. Ejer kan altid se alt."),
    );
    const save = element("button", "", "Gem synlighed");
    save.type = "button";
    save.addEventListener("click", saveRoleVisibility);
    heading.append(text, save);
    const grid = element("div", "module-grid role-visibility-grid");
    grid.id = "roleVisibilityGrid";
    const status = element("p", "panel-help", "Indlæser synlighed…");
    status.id = "roleVisibilityStatus";
    panel.append(heading, grid, status);
    target.append(panel);
    loadRoleVisibility();
  }

  createRoleVisibilityPanel();
  window.loadRoleVisibility = loadRoleVisibility;
})();
