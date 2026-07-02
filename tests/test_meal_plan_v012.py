import os
from datetime import datetime, timezone
from pathlib import Path

from app import config
from app.meal_plan import MealPlanService, meal_days

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
MEAL_JS = (ROOT / "app/static/js/family-meals.js").read_text(encoding="utf-8")
MEAL_CSS = (ROOT / "app/static/css/meal-plan.css").read_text(encoding="utf-8")
MAIN_AUTH = (ROOT / "app/main_auth.py").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")


class FakeCalendarService:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.cleared = False

    def clear_cache(self):
        self.cleared = True

    def get_calendar(self, current_user=None):
        return self.snapshot


class FakeSettings:
    lookahead_days = 3


def test_default_home_assistant_meal_calendar_is_calendar_madplan():
    previous = os.environ.pop("HOME_ASSISTANT_MEAL_CALENDAR", None)
    try:
        assert config.meal_plan_configuration()["entity_id"] == "calendar.madplan"
    finally:
        if previous is not None:
            os.environ["HOME_ASSISTANT_MEAL_CALENDAR"] = previous
    assert "HOME_ASSISTANT_MEAL_CALENDAR=calendar.madplan" in ENV_EXAMPLE


def test_meal_days_group_all_day_and_timed_events_with_exclusive_end():
    now = datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc)
    events = [
        {
            "title": "Lasagne",
            "start": "2026-07-06",
            "end": "2026-07-07",
            "all_day": True,
        },
        {
            "title": "Frikadeller",
            "start": "2026-07-07T17:00:00+00:00",
            "end": "2026-07-07T18:00:00+00:00",
            "all_day": False,
        },
    ]
    days = meal_days(events, 3, now)
    assert days[0] == {"date": "2026-07-06", "label": "I dag", "meals": ["Lasagne"]}
    assert days[1] == {"date": "2026-07-07", "label": "I morgen", "meals": ["Frikadeller"]}
    assert days[2]["meals"] == []


def test_meal_plan_service_hides_details_without_family_authentication():
    service = MealPlanService(
        calendar_service=FakeCalendarService({"status": "ok", "events": [], "stale": False}),
        settings_loader=lambda: FakeSettings(),
        now_provider=lambda: datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
    )
    assert service.get_meal_plan(None) == {
        "status": "authentication_required",
        "days": [],
        "today": [],
        "stale": False,
    }


def test_meal_plan_service_returns_seven_day_style_snapshot_for_family_roles():
    snapshot = {
        "status": "ok",
        "events": [
            {
                "title": "Pizza",
                "start": "2026-07-06",
                "end": "2026-07-07",
                "all_day": True,
            }
        ],
        "stale": False,
    }
    service = MealPlanService(
        calendar_service=FakeCalendarService(snapshot),
        settings_loader=lambda: FakeSettings(),
        now_provider=lambda: datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
    )
    result = service.get_meal_plan({"role": "wall_display"})
    assert result["status"] == "ok"
    assert result["today"] == ["Pizza"]
    assert len(result["days"]) == 3


def test_family_dashboard_loads_meal_plan_without_unsafe_dom_rendering():
    assert 'data-family-card="meal"' in INDEX
    assert 'id="mealPlanToday"' in INDEX
    assert 'id="mealPlanDays"' in INDEX
    assert '/static/css/meal-plan.css' in INDEX
    assert '/static/js/family-meals.js' in INDEX
    assert '/api/family/meal-plan' in MEAL_JS
    assert 'credentials: "same-origin"' in MEAL_JS
    assert "replaceChildren" in MEAL_JS
    for forbidden in ["innerHTML", "insertAdjacentHTML", "localStorage", "sessionStorage", "eval("]:
        assert forbidden not in MEAL_JS
    assert ".meal-plan-today" in MEAL_CSS
    assert 'body[data-family-role="wall_display"]' in MEAL_CSS


def test_meal_plan_router_is_registered_read_only():
    assert "from app.meal_plan import router as meal_plan_router" in MAIN_AUTH
    assert "app.include_router(meal_plan_router)" in MAIN_AUTH
    meal_module = (ROOT / "app/meal_plan.py").read_text(encoding="utf-8")
    assert '@router.get("/api/family/meal-plan")' in meal_module
    assert '@router.post("/api/family/meal-plan")' not in meal_module


if __name__ == "__main__":
    for test in [
        test_default_home_assistant_meal_calendar_is_calendar_madplan,
        test_meal_days_group_all_day_and_timed_events_with_exclusive_end,
        test_meal_plan_service_hides_details_without_family_authentication,
        test_meal_plan_service_returns_seven_day_style_snapshot_for_family_roles,
        test_family_dashboard_loads_meal_plan_without_unsafe_dom_rendering,
        test_meal_plan_router_is_registered_read_only,
    ]:
        test()
    print("Meal plan v0.12 tests OK")
