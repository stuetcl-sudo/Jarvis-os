import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx

from app import config, home_entity_settings
from app.calendar import CalendarConfigurationError, CalendarService, load_calendar_settings
from app.family_tasks import FamilyTasksConfigurationError, FamilyTasksService, load_family_tasks_settings
from app.meal_plan import MealPlanService, load_meal_plan_settings
from app.weather import WeatherConfigurationError, WeatherService, load_weather_settings


@contextmanager
def runtime_environment(**environment):
    names = {
        "HOME_ASSISTANT_URL",
        "HOME_ASSISTANT_TOKEN",
        "HOME_ASSISTANT_WEATHER_ENTITY",
        "HOME_ASSISTANT_CALENDARS",
        "HOME_ASSISTANT_MEAL_CALENDAR",
        "HOME_ASSISTANT_TASK_LISTS",
        "WEATHER_CACHE_SECONDS",
        "WEATHER_STALE_SECONDS",
        "CALENDAR_CACHE_SECONDS",
        "CALENDAR_STALE_SECONDS",
        "MEAL_PLAN_CACHE_SECONDS",
        "MEAL_PLAN_STALE_SECONDS",
    }
    previous_environment = {name: os.environ.get(name) for name in names}
    previous_db = config.DB_PATH
    with tempfile.TemporaryDirectory() as folder:
        config.DB_PATH = str(Path(folder) / "settings.db")
        try:
            for name in names:
                os.environ.pop(name, None)
            os.environ.update({name: str(value) for name, value in environment.items()})
            yield config.DB_PATH
        finally:
            config.DB_PATH = previous_db
            for name, value in previous_environment.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def connection_environment(**extra):
    return runtime_environment(
        HOME_ASSISTANT_URL="https://home-assistant.example",
        HOME_ASSISTANT_TOKEN="".join(["fixture", "-token"]),
        WEATHER_CACHE_SECONDS=10,
        WEATHER_STALE_SECONDS=60,
        CALENDAR_CACHE_SECONDS=10,
        CALENDAR_STALE_SECONDS=60,
        MEAL_PLAN_CACHE_SECONDS=10,
        MEAL_PLAN_STALE_SECONDS=60,
        **extra,
    )


def test_weather_database_precedence_and_legacy_fallback():
    with connection_environment() as db_path:
        home_entity_settings.save_entity_settings({"weather_entity": "weather.database"}, db_path=db_path)
        assert load_weather_settings().entity_id == "weather.database"

    with connection_environment(HOME_ASSISTANT_WEATHER_ENTITY="weather.environment") as db_path:
        home_entity_settings.save_entity_settings({"weather_entity": "weather.database"}, db_path=db_path)
        assert load_weather_settings().entity_id == "weather.database"

    with connection_environment(HOME_ASSISTANT_WEATHER_ENTITY="weather.environment"):
        assert load_weather_settings().entity_id == "weather.environment"


def test_calendar_database_precedence_legacy_fallback_and_empty_calendar():
    with connection_environment() as db_path:
        home_entity_settings.save_entity_settings({"calendar_entities": ["calendar.database"]}, db_path=db_path)
        assert [item.entity_id for item in load_calendar_settings().calendars] == ["calendar.database"]

    legacy = "calendar.environment|Environment|green"
    with connection_environment(HOME_ASSISTANT_CALENDARS=legacy) as db_path:
        home_entity_settings.save_entity_settings({"calendar_entities": ["calendar.database"]}, db_path=db_path)
        assert [item.entity_id for item in load_calendar_settings().calendars] == ["calendar.database"]

    with connection_environment(HOME_ASSISTANT_CALENDARS=legacy):
        assert [item.entity_id for item in load_calendar_settings().calendars] == ["calendar.environment"]

    with connection_environment() as db_path:
        home_entity_settings.save_entity_settings({"calendar_entities": ["calendar.empty"]}, db_path=db_path)

        def empty_calendar(**kwargs):
            return httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=[])), **kwargs)

        result = CalendarService(settings_loader=load_calendar_settings, client_factory=empty_calendar).get_calendar({"role": "owner"})
        assert result["status"] == "ok"
        assert result["events"] == []
        assert result["upcoming_count"] == 0


def test_meal_plan_database_precedence_and_legacy_fallback():
    with connection_environment() as db_path:
        home_entity_settings.save_entity_settings({"meal_calendar": "calendar.database_meals"}, db_path=db_path)
        assert load_meal_plan_settings().calendars[0].entity_id == "calendar.database_meals"

    with connection_environment(HOME_ASSISTANT_MEAL_CALENDAR="calendar.environment_meals") as db_path:
        home_entity_settings.save_entity_settings({"meal_calendar": "calendar.database_meals"}, db_path=db_path)
        assert load_meal_plan_settings().calendars[0].entity_id == "calendar.database_meals"

    with connection_environment(HOME_ASSISTANT_MEAL_CALENDAR="calendar.environment_meals"):
        assert load_meal_plan_settings().calendars[0].entity_id == "calendar.environment_meals"


def test_family_tasks_database_precedence_and_legacy_fallback():
    legacy = "todo.environment|Environment"
    with connection_environment(HOME_ASSISTANT_TASK_LISTS=legacy) as db_path:
        home_entity_settings.save_entity_settings({"task_entities": ["todo.database"]}, db_path=db_path)
        assert [item.entity_id for item in load_family_tasks_settings().sources] == ["todo.database"]

    with connection_environment(HOME_ASSISTANT_TASK_LISTS=legacy):
        assert [item.entity_id for item in load_family_tasks_settings().sources] == ["todo.environment"]


def test_full_admin_save_preserves_legacy_upgrade_values_and_explicit_clear():
    legacy = {
        "HOME_ASSISTANT_WEATHER_ENTITY": "weather.environment",
        "HOME_ASSISTANT_CALENDARS": "calendar.family|Familiekalender|violet,calendar.work|Arbejde|yellow",
        "HOME_ASSISTANT_MEAL_CALENDAR": "calendar.environment_meals",
        "HOME_ASSISTANT_TASK_LISTS": "todo.shopping_list|Indkøb,todo.familieopgaver|Husopgaver",
    }
    with connection_environment(**legacy) as db_path:
        calendars_before = load_calendar_settings().calendars
        tasks_before = load_family_tasks_settings().sources
        assert [(item.entity_id, item.label, item.color) for item in calendars_before] == [
            ("calendar.family", "Familiekalender", "violet"),
            ("calendar.work", "Arbejde", "yellow"),
        ]
        assert [(item.entity_id, item.label) for item in tasks_before] == [
            ("todo.shopping_list", "Indkøb"),
            ("todo.familieopgaver", "Husopgaver"),
        ]

        edit_values = home_entity_settings.load_effective_entity_settings(db_path=db_path)
        edit_values["electricity_price_entity"] = "sensor.database_price"
        edit_values.pop("calendar_entities")
        edit_values.pop("task_entities")
        home_entity_settings.save_entity_settings(edit_values, db_path=db_path)

        assert load_weather_settings().entity_id == "weather.environment"
        calendars_after = load_calendar_settings().calendars
        tasks_after = load_family_tasks_settings().sources
        assert [(item.entity_id, item.label, item.color) for item in calendars_after] == [
            ("calendar.family", "Familiekalender", "violet"),
            ("calendar.work", "Arbejde", "yellow"),
        ]
        assert load_meal_plan_settings().calendars[0].entity_id == "calendar.environment_meals"
        assert [(item.entity_id, item.label) for item in tasks_after] == [
            ("todo.shopping_list", "Indkøb"),
            ("todo.familieopgaver", "Husopgaver"),
        ]
        missing = object()
        assert home_entity_settings.settings_store.get_setting(
            "home_assistant.calendar_entities", missing, db_path=db_path
        ) is missing
        assert home_entity_settings.settings_store.get_setting(
            "home_assistant.task_entities", missing, db_path=db_path
        ) is missing

        home_entity_settings.save_entity_settings(
            {"weather_entity": "weather.database"}, db_path=db_path
        )
        assert load_weather_settings().entity_id == "weather.database"

        home_entity_settings.save_entity_settings(
            {
                "calendar_entities": ["calendar.database"],
                "task_entities": ["todo.database"],
            },
            db_path=db_path,
        )
        assert [item.entity_id for item in load_calendar_settings().calendars] == ["calendar.database"]
        assert [item.entity_id for item in load_family_tasks_settings().sources] == ["todo.database"]

        home_entity_settings.save_entity_settings(
            {"meal_calendar": "", "calendar_entities": [], "task_entities": []},
            db_path=db_path,
        )
        assert load_meal_plan_settings() is None
        assert load_calendar_settings() is None
        assert load_family_tasks_settings() is None
        assert home_entity_settings.load_effective_entity_settings(db_path=db_path)["meal_calendar"] == ""


def test_empty_legacy_round_trip_and_explicit_list_clears_are_distinct():
    with connection_environment(
        HOME_ASSISTANT_CALENDARS="",
        HOME_ASSISTANT_TASK_LISTS="",
    ) as db_path:
        edit_values = home_entity_settings.load_effective_entity_settings(db_path=db_path)
        assert edit_values["calendar_entities"] == []
        assert edit_values["task_entities"] == []

        unrelated_save = {**edit_values, "electricity_price_entity": "sensor.database_price"}
        unrelated_save.pop("calendar_entities")
        unrelated_save.pop("task_entities")
        home_entity_settings.save_entity_settings(unrelated_save, db_path=db_path)
        missing = object()
        assert home_entity_settings.settings_store.get_setting(
            "home_assistant.calendar_entities", missing, db_path=db_path
        ) is missing
        assert home_entity_settings.settings_store.get_setting(
            "home_assistant.task_entities", missing, db_path=db_path
        ) is missing

        home_entity_settings.save_entity_settings(
            {"calendar_entities": [], "task_entities": []}, db_path=db_path
        )
        os.environ["HOME_ASSISTANT_CALENDARS"] = "calendar.future|Future calendar|yellow"
        os.environ["HOME_ASSISTANT_TASK_LISTS"] = "todo.future|Future tasks"

        assert load_calendar_settings() is None
        assert load_family_tasks_settings() is None
        assert home_entity_settings.load_effective_entity_settings(db_path=db_path)["calendar_entities"] == []
        assert home_entity_settings.load_effective_entity_settings(db_path=db_path)["task_entities"] == []


def test_database_errors_never_use_environment_fallbacks():
    for error_type in (OSError, RuntimeError):
        private_detail = f"private-{error_type.__name__}-database-path"
        with patch(
            "app.home_entity_settings.settings_store.get_setting",
            side_effect=error_type(private_detail),
        ):
            try:
                home_entity_settings.runtime_entity_setting(
                    "weather_entity", "weather.environment", db_path="private.db"
                )
            except error_type as exc:
                assert str(exc) == private_detail
            else:
                raise AssertionError("Database failure incorrectly used the environment fallback")


def test_runtime_services_map_database_errors_to_safe_states():
    cases = [
        (
            "home_assistant.weather_entity",
            load_weather_settings,
            WeatherConfigurationError,
            lambda: WeatherService(settings_loader=load_weather_settings).get_weather(),
            None,
        ),
        (
            "home_assistant.calendar_entities",
            load_calendar_settings,
            CalendarConfigurationError,
            lambda: CalendarService(settings_loader=load_calendar_settings).get_calendar({"role": "owner"}),
            "calendar.environment|Environment|green",
        ),
        (
            "home_assistant.meal_calendar",
            load_meal_plan_settings,
            CalendarConfigurationError,
            lambda: MealPlanService(settings_loader=load_meal_plan_settings).get_meal_plan({"role": "owner"}),
            None,
        ),
        (
            "home_assistant.task_entities",
            load_family_tasks_settings,
            FamilyTasksConfigurationError,
            lambda: FamilyTasksService(
                settings_loader=load_family_tasks_settings,
                people_loader=lambda: [],
            ).get_tasks({"role": "owner"}),
            None,
        ),
    ]
    environment_values = {
        "HOME_ASSISTANT_WEATHER_ENTITY": "weather.environment",
        "HOME_ASSISTANT_CALENDARS": "calendar.environment|Environment|green",
        "HOME_ASSISTANT_MEAL_CALENDAR": "calendar.environment_meals",
        "HOME_ASSISTANT_TASK_LISTS": "todo.environment|Environment",
    }
    with connection_environment(**environment_values):
        original_get = home_entity_settings.settings_store.get_setting
        for key, loader, expected_error, service_call, _fallback in cases:
            private_detail = f"private failure for {key}"

            def failing_get(requested_key, default=None, db_path=None, *, target=key, detail=private_detail):
                if requested_key == target:
                    raise OSError(detail)
                return original_get(requested_key, default, db_path=db_path)

            with patch("app.home_entity_settings.settings_store.get_setting", side_effect=failing_get):
                try:
                    loader()
                except expected_error as exc:
                    assert private_detail not in str(exc)
                else:
                    raise AssertionError(f"{key} database failure did not become a configuration error")
                result = service_call()
            assert result["status"] == "unavailable"
            assert private_detail not in repr(result)


if __name__ == "__main__":
    test_weather_database_precedence_and_legacy_fallback()
    test_calendar_database_precedence_legacy_fallback_and_empty_calendar()
    test_meal_plan_database_precedence_and_legacy_fallback()
    test_family_tasks_database_precedence_and_legacy_fallback()
    test_full_admin_save_preserves_legacy_upgrade_values_and_explicit_clear()
    test_empty_legacy_round_trip_and_explicit_list_clears_are_distinct()
    test_database_errors_never_use_environment_fallbacks()
    test_runtime_services_map_database_errors_to_safe_states()
    print("Runtime entity settings tests OK")
