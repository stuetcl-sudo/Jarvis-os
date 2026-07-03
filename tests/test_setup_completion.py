import os
import tempfile
from pathlib import Path

from app import home_entity_settings, home_setup


ROOT = Path(__file__).resolve().parents[1]


def test_setup_summary_contains_entity_breakdown():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        home_setup.save_home_settings("Mit hjem", "Europe/Copenhagen", "Ejer", db_path=db_path)
        home_entity_settings.save_entity_settings(
            {
                "calendar_entities": ["calendar.family"],
                "meal_calendar": "calendar.meals",
                "task_entities": ["todo.shopping"],
                "weather_entity": "weather.home",
                "electricity_price_entity": "sensor.price",
                "power_entity": "sensor.power",
                "energy_entity": "",
                "temperature_entities": ["sensor.living_room_temperature"],
                "humidity_entities": ["sensor.living_room_humidity"],
            },
            db_path=db_path,
        )
        summary = home_setup.setup_summary(db_path=db_path)
        assert summary["selected_entity_count"] == 8
        assert summary["entity_breakdown"] == {
            "calendars": 2,
            "task_lists": 1,
            "weather": 1,
            "energy_sources": 2,
            "climate_sensors": 2,
        }
        assert summary["ready_to_complete"] is True


def test_completion_frontend_contract():
    html = (ROOT / "app/static/setup.html").read_text(encoding="utf-8")
    source = (ROOT / "app/static/js/setup-completion.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "app/static/css/setup.css").read_text(encoding="utf-8")

    assert '/static/js/setup-completion.js' in html
    assert '"/api/admin/setup/summary"' in source
    assert "entity_breakdown" in source
    assert "setup-check" in source
    assert ".setup-check.ok" in stylesheet
    assert ".setup-check.warning" in stylesheet
    assert ".setup-check.optional" in stylesheet
    assert "innerHTML" not in source


def test():
    test_setup_summary_contains_entity_breakdown()
    test_completion_frontend_contract()
    print("Setup completion tests OK")


if __name__ == "__main__":
    test()
