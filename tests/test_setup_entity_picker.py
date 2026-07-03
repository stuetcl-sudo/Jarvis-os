from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_setup_entity_picker_contract():
    source = (ROOT / "app/static/js/setup.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "app/static/css/setup.css").read_text(encoding="utf-8")

    assert 'id = "setupEntitySelectorGrid"' in source
    assert '"/api/admin/setup/home-assistant/entities"' in source
    assert '"/api/admin/setup/home-assistant/entity-settings"' in source
    assert 'credentials = "same-origin"' in source
    assert "setupSelections[key].add" in source
    assert "setupSelections[key].delete" in source
    assert "Vis tekniske sensorer" in source
    assert ".entity-selector-grid" in stylesheet
    assert ".entity-checkbox-row" in stylesheet


def test():
    test_setup_entity_picker_contract()
    print("Setup entity picker tests OK")


if __name__ == "__main__":
    test()
