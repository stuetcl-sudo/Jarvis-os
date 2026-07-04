from datetime import date, datetime, time as datetime_time, timedelta

from fastapi import APIRouter, Request

from app import config
from app.calendar import (
    CALENDAR_ENTITY_RE,
    CalendarConfigurationError,
    CalendarService,
    CalendarSettings,
    CalendarSource,
)
from app.family_visibility import family_feature_hidden
from app.home_assistant import (
    HomeAssistantConfigurationError,
    load_home_assistant_connection,
)

AUTHENTICATED_ROLES = {"owner", "adult", "child", "wall_display"}
WEEKDAY_LABELS = ("Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag")


def load_meal_plan_settings():
    try:
        values = config.meal_plan_configuration()
    except ValueError as exc:
        raise CalendarConfigurationError("Meal plan configuration is invalid") from exc

    entity_id = values["entity_id"]
    if not entity_id:
        return None
    if not CALENDAR_ENTITY_RE.fullmatch(entity_id):
        raise CalendarConfigurationError("Meal plan calendar entity is invalid")

    try:
        connection = load_home_assistant_connection()
    except HomeAssistantConfigurationError as exc:
        raise CalendarConfigurationError("Meal plan configuration is invalid") from exc
    if connection is None:
        return None
    if values["stale_seconds"] < values["cache_seconds"]:
        raise CalendarConfigurationError("MEAL_PLAN_STALE_SECONDS must be at least MEAL_PLAN_CACHE_SECONDS")

    return CalendarSettings(
        connection=connection,
        calendars=(CalendarSource(entity_id, "meal-plan", "Madplan", "yellow"),),
        lookahead_days=values["lookahead_days"],
        cache_seconds=values["cache_seconds"],
        stale_seconds=values["stale_seconds"],
        max_events=values["max_events"],
    )


def _local_now(value=None):
    current = value or datetime.now().astimezone()
    local_tz = current.tzinfo or datetime.now().astimezone().tzinfo
    if current.tzinfo is None:
        current = current.replace(tzinfo=local_tz)
    return current.astimezone(local_tz), local_tz


def _event_bounds(event, local_tz):
    try:
        if event.get("all_day"):
            start_date = date.fromisoformat(event["start"])
            end_date = date.fromisoformat(event["end"])
            return (
                datetime.combine(start_date, datetime_time.min, tzinfo=local_tz),
                datetime.combine(end_date, datetime_time.min, tzinfo=local_tz),
            )
        start = datetime.fromisoformat(event["start"])
        end = datetime.fromisoformat(event["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=local_tz)
    if end.tzinfo is None:
        end = end.replace(tzinfo=local_tz)
    return start.astimezone(local_tz), end.astimezone(local_tz)


def _day_label(day, today):
    if day == today:
        return "I dag"
    if day == today + timedelta(days=1):
        return "I morgen"
    return WEEKDAY_LABELS[day.weekday()]


def meal_days(events, lookahead_days, now=None):
    current, local_tz = _local_now(now)
    result = []
    for offset in range(lookahead_days):
        day = current.date() + timedelta(days=offset)
        day_start = datetime.combine(day, datetime_time.min, tzinfo=local_tz)
        day_end = day_start + timedelta(days=1)
        meals = []
        for event in events:
            bounds = _event_bounds(event, local_tz)
            if bounds is None or bounds[0] >= day_end or bounds[1] <= day_start:
                continue
            title = " ".join(str(event.get("title") or "").split())
            if title and title not in meals:
                meals.append(title)
        result.append(
            {
                "date": day.isoformat(),
                "label": _day_label(day, current.date()),
                "meals": meals,
            }
        )
    return result


def empty_meal_plan(status):
    return {
        "status": status,
        "days": [],
        "today": [],
        "stale": False,
    }


class MealPlanService:
    def __init__(
        self,
        calendar_service=None,
        settings_loader=load_meal_plan_settings,
        now_provider=lambda: datetime.now().astimezone(),
    ):
        self.settings_loader = settings_loader
        self.now_provider = now_provider
        self.calendar_service = calendar_service or CalendarService(
            settings_loader=settings_loader,
            now_provider=now_provider,
        )

    def clear_cache(self):
        self.calendar_service.clear_cache()

    def get_meal_plan(self, current_user=None):
        if family_feature_hidden(current_user, "meal"):
            return empty_meal_plan("hidden")
        authenticated = (
            isinstance(current_user, dict)
            and current_user.get("role") in AUTHENTICATED_ROLES
        )
        if not authenticated:
            return empty_meal_plan("authentication_required")

        snapshot = self.calendar_service.get_calendar(current_user)
        try:
            settings = self.settings_loader()
        except CalendarConfigurationError:
            settings = None
        lookahead_days = settings.lookahead_days if settings is not None else 7

        if snapshot["status"] in {"not_configured", "unavailable", "hidden"}:
            return {
                "status": snapshot["status"],
                "days": [],
                "today": [],
                "stale": bool(snapshot.get("stale")),
            }

        days = meal_days(snapshot.get("events", []), lookahead_days, self.now_provider())
        return {
            "status": snapshot["status"],
            "days": days,
            "today": days[0]["meals"] if days else [],
            "stale": bool(snapshot.get("stale")),
        }


meal_plan_service = MealPlanService()
router = APIRouter()


@router.get("/api/family/meal-plan")
def family_meal_plan(request: Request):
    current_user = getattr(request.state, "current_user", None)
    return meal_plan_service.get_meal_plan(current_user)
