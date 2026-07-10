import os
import tempfile

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


def test():
    test_round_trip()
    test_partial_update_preserves_omitted_fields()
    test_explicit_empty_value_clears_only_requested_field()
    test_wrong_type_rejected()
    test_safety_wrong_type_rejected()
    print("Home entity settings tests OK")


if __name__ == "__main__":
    test()
