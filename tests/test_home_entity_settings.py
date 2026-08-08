import os
import tempfile
from unittest.mock import patch

from app import home_entity_settings


def test_round_trip():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        values = {
            "calendar_entities": ["calendar.family"],
            "meal_calendar": "calendar.meals",
            "task_entities": ["todo.shopping_list"],
            "weather_entity": "weather.home",
            "internet_status_entity": "sensor.gateway_state",
            "electricity_price_entity": "sensor.price",
            "power_entity": "sensor.power",
            "energy_entity": "sensor.energy",
            "temperature_entities": ["sensor.temperature"],
            "humidity_entities": ["sensor.humidity"],
            "safety_door_entities": ["binary_sensor.back_door", "binary_sensor.back_door"],
            "safety_motion_entities": ["binary_sensor.hall_motion"],
            "safety_camera_entities": ["camera.driveway"],
        }
        saved = home_entity_settings.save_entity_settings(values, db_path=db_path)
        assert saved["internet_status_entity"] == "sensor.gateway_state"
        assert saved["safety_door_entities"] == ["binary_sensor.back_door"]
        assert home_entity_settings.load_entity_settings(db_path=db_path) == saved


def test_partial_update_preserves_omitted_fields():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        home_entity_settings.save_entity_settings(
            {
                "internet_status_entity": "sensor.gateway_state",
                "temperature_entities": ["sensor.living_temperature"],
                "humidity_entities": ["sensor.living_humidity"],
            },
            db_path=db_path,
        )
        saved = home_entity_settings.save_entity_settings(
            {"electricity_price_entity": "sensor.price"},
            db_path=db_path,
        )
        assert saved["internet_status_entity"] == "sensor.gateway_state"
        assert saved["temperature_entities"] == ["sensor.living_temperature"]
        assert saved["humidity_entities"] == ["sensor.living_humidity"]
        assert saved["electricity_price_entity"] == "sensor.price"


def test_explicit_empty_value_clears_only_requested_field():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        home_entity_settings.save_entity_settings(
            {
                "internet_status_entity": "sensor.gateway_state",
                "temperature_entities": ["sensor.living_temperature"],
            },
            db_path=db_path,
        )
        saved = home_entity_settings.save_entity_settings(
            {"internet_status_entity": ""},
            db_path=db_path,
        )
        assert saved["internet_status_entity"] == ""
        assert saved["temperature_entities"] == ["sensor.living_temperature"]


def test_wrong_type_rejected():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        try:
            home_entity_settings.save_entity_settings({"meal_calendar": "sensor.wrong"}, db_path=db_path)
        except ValueError:
            return
        raise AssertionError("Wrong entity type was accepted")


def test_safety_wrong_type_rejected():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        try:
            home_entity_settings.save_entity_settings(
                {"safety_door_entities": ["sensor.not_a_door"]},
                db_path=db_path,
            )
        except ValueError:
            return
        raise AssertionError("Wrong safety entity type was accepted")


def test_effective_edit_values_preserve_legacy_fallbacks_and_explicit_clears():
    legacy = {
        "HOME_ASSISTANT_WEATHER_ENTITY": "weather.legacy_home",
        "HOME_ASSISTANT_CALENDARS": "calendar.family|Familiekalender|violet,calendar.work|Arbejde|yellow",
        "HOME_ASSISTANT_MEAL_CALENDAR": "calendar.legacy_meals",
        "HOME_ASSISTANT_TASK_LISTS": "todo.shopping_list|Indkøb,todo.familieopgaver|Husopgaver",
    }
    with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, legacy):
        db_path = os.path.join(folder, "jarvis.db")
        effective = home_entity_settings.load_effective_entity_settings(db_path=db_path)
        assert effective["weather_entity"] == "weather.legacy_home"
        assert effective["calendar_entities"] == ["calendar.family", "calendar.work"]
        assert effective["meal_calendar"] == "calendar.legacy_meals"
        assert effective["task_entities"] == ["todo.shopping_list", "todo.familieopgaver"]

        submitted = {**effective, "electricity_price_entity": "sensor.current_price"}
        submitted.pop("calendar_entities")
        submitted.pop("task_entities")
        home_entity_settings.save_entity_settings(submitted, db_path=db_path)
        reloaded = home_entity_settings.load_effective_entity_settings(db_path=db_path)
        assert reloaded["weather_entity"] == "weather.legacy_home"
        assert reloaded["calendar_entities"] == ["calendar.family", "calendar.work"]
        assert reloaded["meal_calendar"] == "calendar.legacy_meals"
        assert reloaded["task_entities"] == ["todo.shopping_list", "todo.familieopgaver"]
        missing = object()
        assert home_entity_settings.settings_store.get_setting(
            "home_assistant.calendar_entities", missing, db_path=db_path
        ) is missing
        assert home_entity_settings.settings_store.get_setting(
            "home_assistant.task_entities", missing, db_path=db_path
        ) is missing

        home_entity_settings.save_entity_settings(
            {"weather_entity": "weather.new_home"}, db_path=db_path
        )
        assert home_entity_settings.load_effective_entity_settings(db_path=db_path)["weather_entity"] == "weather.new_home"

        home_entity_settings.save_entity_settings({"calendar_entities": []}, db_path=db_path)
        reloaded_after_clear = home_entity_settings.load_effective_entity_settings(db_path=db_path)
        assert reloaded_after_clear["calendar_entities"] == []
        assert home_entity_settings.runtime_entity_setting(
            "calendar_entities", ["calendar.family", "calendar.work"], db_path=db_path
        ) == []


def test():
    test_round_trip()
    test_partial_update_preserves_omitted_fields()
    test_explicit_empty_value_clears_only_requested_field()
    test_wrong_type_rejected()
    test_safety_wrong_type_rejected()
    test_effective_edit_values_preserve_legacy_fallbacks_and_explicit_clears()
    print("Home entity settings tests OK")


if __name__ == "__main__":
    test()
