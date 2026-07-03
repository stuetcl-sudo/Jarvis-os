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
        }
        saved = home_entity_settings.save_entity_settings(values, db_path=db_path)
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
        }
        try:
            home_entity_settings.save_entity_settings(values, db_path=db_path)
        except ValueError:
            return
        raise AssertionError("Wrong entity type was accepted")


def test():
    test_round_trip()
    test_wrong_type_rejected()
    print("Home entity settings tests OK")


if __name__ == "__main__":
    test()
