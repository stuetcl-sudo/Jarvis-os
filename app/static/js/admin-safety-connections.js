function safetyDeviceClassMatches(item, accepted) {
  return accepted.includes(item.device_class);
}

function safetyMatchingEntities(type, acceptedDeviceClasses = null) {
  return discoveredHomeAssistantEntities.filter((item) => {
    if (item.domain !== type) return false;
    if (acceptedDeviceClasses && !safetyDeviceClassMatches(item, acceptedDeviceClasses)) return false;
    if (!showTechnicalHomeAssistantEntities && isLikelyTechnicalEntity(item)) return false;
    return true;
  });
}

function createSafetyInfoCard() {
  const card = element("section", "entity-picker-card");
  card.append(
    element("h5", "", "Internet"),
    element("p", "panel-help", "Internetstatus bliver kontrolleret automatisk og vises som Online, Ustabil eller Offline på vægskærmen."),
  );
  return card;
}

function createSafetyCheckboxPicker(id, label, type, acceptedDeviceClasses = null, helpText = "") {
  const card = element("section", "entity-picker-card");
  const title = element("h5", "", label);
  const searchLabel = element("label", "visually-hidden", `Søg i ${label}`);
  const search = element("input");
  search.type = "search";
  search.placeholder = `Søg i ${label.toLowerCase()}…`;
  searchLabel.append(search);

  const list = element("div", "entity-checkbox-list");
  list.id = id;
  list.dataset.picker = "true";
  const items = safetyMatchingEntities(type, acceptedDeviceClasses);

  function render(query = "") {
    const needle = query.trim().toLowerCase();
    const visible = items.filter((item) => {
      const haystack = `${item.name || ""} ${item.entity_id || ""}`.toLowerCase();
      return !needle || haystack.includes(needle);
    });
    const previouslyChecked = new Set(
      Array.from(list.querySelectorAll('input[type="checkbox"]:checked')).map((input) => input.value),
    );
    const rows = visible.map((item) => {
      const row = element("label", "entity-checkbox-row");
      const checkbox = element("input");
      checkbox.type = "checkbox";
      checkbox.value = item.entity_id;
      checkbox.checked = previouslyChecked.has(item.entity_id);
      const text = element("span", "entity-checkbox-text");
      text.append(
        element("strong", "", entityTitle(item)),
        element("small", "", item.entity_id),
      );
      row.append(checkbox, text);
      return row;
    });
    list.replaceChildren(...(rows.length ? rows : [element("p", "muted", "Ingen matchende entiteter.")]));
  }

  search.addEventListener("input", () => render(search.value));
  render();
  card.append(title);
  if (helpText) card.append(element("p", "panel-help", helpText));
  card.append(searchLabel, search, list);
  return card;
}

function appendSafetySelectors() {
  const grid = document.getElementById("homeAssistantSelectorGrid");
  if (!grid) return;
  grid.append(
    createSafetyInfoCard(),
    createSafetyCheckboxPicker("haSafetyDoorEntities", "Døre og vinduer", "binary_sensor", ["door", "window", "opening", "garage_door"]),
    createSafetyCheckboxPicker(
      "haSafetyMotionEntities",
      "Bevægelse",
      "binary_sensor",
      null,
      "Viser alle binary sensors, så Zigbee/PIR-sensorer uden korrekt type også kan vælges. Søg fx efter motion, bevægelse, PIR eller presence.",
    ),
    createSafetyCheckboxPicker("haSafetyCameraEntities", "Kameraer", "camera"),
  );
}

const baseRenderHomeAssistantSelectors = renderHomeAssistantSelectors;
renderHomeAssistantSelectors = function renderHomeAssistantSelectorsWithSafety() {
  baseRenderHomeAssistantSelectors();
  appendSafetySelectors();
};

const baseApplyHomeAssistantEntitySettings = applyHomeAssistantEntitySettings;
applyHomeAssistantEntitySettings = function applyHomeAssistantEntitySettingsWithSafety(settings) {
  baseApplyHomeAssistantEntitySettings(settings);
  setSelectedValues("haSafetyDoorEntities", settings.safety_door_entities);
  setSelectedValues("haSafetyMotionEntities", settings.safety_motion_entities);
  setSelectedValues("haSafetyCameraEntities", settings.safety_camera_entities);
};

const baseHomeAssistantEntitySettingsPayload = homeAssistantEntitySettingsPayload;
homeAssistantEntitySettingsPayload = function homeAssistantEntitySettingsPayloadWithSafety() {
  return {
    ...baseHomeAssistantEntitySettingsPayload(),
    safety_door_entities: selectedValues("haSafetyDoorEntities"),
    safety_motion_entities: selectedValues("haSafetyMotionEntities"),
    safety_camera_entities: selectedValues("haSafetyCameraEntities"),
  };
};
