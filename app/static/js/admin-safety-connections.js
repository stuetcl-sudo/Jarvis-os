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

function createInternetStatusSelect() {
  const card = element("section", "entity-picker-card");
  const fieldLabel = element("label", "filter-label", "Internet");
  fieldLabel.htmlFor = "haInternetStatusEntity";
  const select = element("select");
  select.id = "haInternetStatusEntity";
  const empty = element("option", "", "Ikke valgt");
  empty.value = "";
  select.append(empty);
  discoveredHomeAssistantEntities
    .filter((item) => {
      if (!["sensor", "binary_sensor"].includes(item.domain)) return false;
      if (!showTechnicalHomeAssistantEntities && isLikelyTechnicalEntity(item)) return false;
      return true;
    })
    .forEach((item) => {
      const option = element("option", "", entityTitle(item));
      option.value = item.entity_id;
      option.title = item.entity_id;
      select.append(option);
    });
  const help = element(
    "p",
    "panel-help",
    "Vælg fx gatewayens state/status-sensor. Connected, online, up eller ok vises som Online på vægskærmen.",
  );
  fieldLabel.append(select);
  card.append(fieldLabel, help);
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
    createInternetStatusSelect(),
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
  const internetSelect = document.getElementById("haInternetStatusEntity");
  if (internetSelect) internetSelect.value = settings.internet_status_entity || "";
  setSelectedValues("haSafetyDoorEntities", settings.safety_door_entities);
  setSelectedValues("haSafetyMotionEntities", settings.safety_motion_entities);
  setSelectedValues("haSafetyCameraEntities", settings.safety_camera_entities);
};

const baseHomeAssistantEntitySettingsPayload = homeAssistantEntitySettingsPayload;
homeAssistantEntitySettingsPayload = function homeAssistantEntitySettingsPayloadWithSafety() {
  return {
    ...baseHomeAssistantEntitySettingsPayload(),
    internet_status_entity: document.getElementById("haInternetStatusEntity")?.value || "",
    safety_door_entities: selectedValues("haSafetyDoorEntities"),
    safety_motion_entities: selectedValues("haSafetyMotionEntities"),
    safety_camera_entities: selectedValues("haSafetyCameraEntities"),
  };
};
