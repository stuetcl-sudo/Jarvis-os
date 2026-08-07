(() => {
  const moduleLabels = {
    calendar: "Kalender",
    tasks: "Opgaver",
    routines: "Rutiner",
    meal_plan: "Madplan",
    weather: "Vejr",
    safety: "Status for hjemmet",
  };
  let moduleSettings = null;

  function renderModuleSettings() {
    const target = document.getElementById("familyModuleSettings");
    if (!target || !moduleSettings) return;
    const controls = Object.entries(moduleLabels).map(([module, labelText]) => {
      const label = element("label", "module-card checkbox-control");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.dataset.familyModule = module;
      input.checked = moduleSettings[module] !== false;
      label.append(input, document.createTextNode(` ${labelText}`));
      return label;
    });
    replaceContent(target, controls);
  }

  function collectModuleSettings() {
    const modules = {};
    Object.keys(moduleLabels).forEach((module) => {
      modules[module] = document.querySelector(`[data-family-module="${module}"]`)?.checked === true;
    });
    return modules;
  }

  async function loadModuleSettings() {
    const status = document.getElementById("familyModuleSettingsStatus");
    try {
      const data = await getJson("/api/admin/modules");
      moduleSettings = data.modules || {};
      renderModuleSettings();
      status.textContent = "";
    } catch (_error) {
      status.textContent = "Modulindstillingerne kunne ikke hentes.";
    }
  }

  async function saveModuleSettings() {
    const button = document.getElementById("saveFamilyModulesButton");
    const status = document.getElementById("familyModuleSettingsStatus");
    button.disabled = true;
    try {
      const data = await getJson("/api/admin/modules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ modules: collectModuleSettings() }),
      });
      moduleSettings = data.modules || {};
      renderModuleSettings();
      status.textContent = "Modulindstillingerne er gemt.";
      showNotice("Modulindstillingerne er gemt.", "success");
    } catch (_error) {
      status.textContent = "Modulindstillingerne kunne ikke gemmes. Prøv igen.";
      showNotice("Modulindstillingerne kunne ikke gemmes. Prøv igen.", "error", 0);
    } finally {
      button.disabled = false;
    }
  }

  document.getElementById("saveFamilyModulesButton")?.addEventListener("click", saveModuleSettings);
  loadModuleSettings();
})();
