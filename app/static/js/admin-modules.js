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
  let moduleConfig = null;

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

  function renderModuleConfig() {
    if (!moduleConfig) return;
    const moduleList = document.getElementById("familyModuleSettings");
    if (!document.getElementById("calendarDaysSetting")) {
      const settings = element("div", "content-grid two-columns");
      settings.setAttribute("aria-label", "Indstillinger for familiens moduler");
      const daySelect = (id, text) => {
        const label = element("label", "", text + " ");
        const select = document.createElement("select");
        select.id = id;
        for (let day = 1; day <= 7; day += 1) {
          const option = document.createElement("option");
          option.value = String(day);
          option.textContent = `${day} ${day === 1 ? "dag" : "dage"}`;
          select.append(option);
        }
        label.append(select);
        return label;
      };
      const uvLabel = element("label", "checkbox-control");
      const uvInput = document.createElement("input");
      uvInput.id = "weatherUvSetting";
      uvInput.type = "checkbox";
      uvLabel.append(uvInput, document.createTextNode(" Vis UV-vejledning i vejret"));
      settings.append(daySelect("calendarDaysSetting", "Kalenderdage"), daySelect("mealPlanDaysSetting", "Madplansdage"), uvLabel);
      moduleList?.insertAdjacentElement("afterend", settings);
    }
    document.getElementById("calendarDaysSetting").value = String(moduleConfig.calendar_days ?? 3);
    document.getElementById("mealPlanDaysSetting").value = String(moduleConfig.meal_plan_days ?? 7);
    document.getElementById("weatherUvSetting").checked = moduleConfig.weather_uv_enabled !== false;
  }

  function collectModuleConfig() {
    return {
      calendar_days: Number(document.getElementById("calendarDaysSetting").value),
      meal_plan_days: Number(document.getElementById("mealPlanDaysSetting").value),
      weather_uv_enabled: document.getElementById("weatherUvSetting").checked,
    };
  }

  async function loadModuleSettings() {
    const status = document.getElementById("familyModuleSettingsStatus");
    try {
      const data = await getJson("/api/admin/modules");
      moduleSettings = data.modules || {};
      moduleConfig = data.config || {};
      renderModuleSettings();
      renderModuleConfig();
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
        body: JSON.stringify({ modules: collectModuleSettings(), config: collectModuleConfig() }),
      });
      moduleSettings = data.modules || {};
      moduleConfig = data.config || {};
      renderModuleSettings();
      renderModuleConfig();
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
