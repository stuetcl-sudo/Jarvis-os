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
        assert saved["safety_door_entities"] == ["binary_sensor.back_door"]
        assert home_entity_settings.load_entity_settings(db_path=db_path) == saved


def test_wrong_type_rejected():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        values = {
            "calendar_entities": [],
            "meal_calendar": "sensor.wrong",
            "task_entities": [],
            "temperature_entities": [],
            "humidity_entities": [],
            "safety_door_entities": [],
            "safety_motion_entities": [],
            "safety_camera_entities": [],
        }
        try:
            home_entity_settings.save_entity_settings(values, db_path=db_path)
        except ValueError:
            return
        raise AssertionError("Wrong entity type was accepted")


def test_safety_wrong_type_rejected():
    with tempfile.TemporaryDirectory() as folder:
        db_path = os.path.join(folder, "jarvis.db")
        values = {
            "safety_door_entities": ["sensor.not_a_door"],
            "safety_motion_entities": [],
            "safety_camera_entities": [],
        }
        try:
            home_entity_settings.save_entity_settings(values, db_path=db_path)
        except ValueError:
            return
        raise AssertionError("Wrong safety entity type was accepted")


def test():
    test_round_trip()
    test_wrong_type_rejected()
    test_safety_wrong_type_rejected()
    print("Home entity settings tests OK")


if __name__ == "__main__":
    test()
