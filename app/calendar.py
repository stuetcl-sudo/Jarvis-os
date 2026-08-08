import copy
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Callable
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Request

from app import config, home_entity_settings
from app.family_visibility import family_feature_hidden
from app.home_assistant import (
    HomeAssistantClient,
    HomeAssistantConfigurationError,
    HomeAssistantUnavailable,
    load_home_assistant_connection,
)

CALENDAR_ENTITY_RE = re.compile(r"^calendar\.[a-z0-9_]+$")
SUPPORTED_COLORS = {"green", "blue", "violet", "yellow"}
AUTHENTICATED_ROLES = {"owner", "adult", "child", "wall_display"}
MAX_LABEL_LENGTH = 32
MAX_TITLE_LENGTH = 120


class CalendarConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class CalendarSource:
    entity_id: str = field(repr=False)
    key: str
    label: str
    color: str


@dataclass(frozen=True)
class CalendarSettings:
    connection: object = field(repr=False)
    calendars: tuple[CalendarSource, ...]
    lookahead_days: int
    cache_seconds: int
    stale_seconds: int
    max_events: int

    def signature(self):
        return (
            self.connection.base_url,
            tuple((item.entity_id, item.key, item.label, item.color) for item in self.calendars),
            self.lookahead_days,
            self.cache_seconds,
            self.stale_seconds,
            self.max_events,
        )


def _plain_label(value):
    label = " ".join(value.strip().split())
    if not label or len(label) > MAX_LABEL_LENGTH:
        raise CalendarConfigurationError("Calendar label is invalid")
    if any(not (character.isalnum() or character in " ._-'ÆØÅæøå") for character in label):
        raise CalendarConfigurationError("Calendar label is invalid")
    return label


def _calendar_key(label, used):
    normalized = unicodedata.normalize("NFKD", label)
    ascii_label = normalized.encode("ascii", "ignore").decode("ascii").lower()
    base = re.sub(r"[^a-z0-9]+", "-", ascii_label).strip("-") or "calendar"
    key = base
    suffix = 2
    while key in used:
        key = f"{base}-{suffix}"
        suffix += 1
    used.add(key)
    return key


def parse_calendar_sources(raw_value):
    sources = []
    seen_entities = set()
    used_keys = set()
    for raw_entry in raw_value.split(","):
        parts = [part.strip() for part in raw_entry.split("|")]
        if len(parts) != 3 or any(not part for part in parts):
            raise CalendarConfigurationError("Calendar mapping is invalid")
        entity_id, raw_label, color = parts
        if not CALENDAR_ENTITY_RE.fullmatch(entity_id):
            raise CalendarConfigurationError("Calendar entity is invalid")
        if entity_id in seen_entities:
            raise CalendarConfigurationError("Calendar entity is duplicated")
        if color not in SUPPORTED_COLORS:
            raise CalendarConfigurationError("Calendar color is invalid")
        label = _plain_label(raw_label)
        seen_entities.add(entity_id)
        sources.append(CalendarSource(entity_id, _calendar_key(label, used_keys), label, color))
    if not sources:
        raise CalendarConfigurationError("Calendar mapping is empty")
    return tuple(sources)


def calendar_sources_from_entities(entity_ids):
    colors = ("green", "blue", "violet", "yellow")
    used_keys = set()
    return tuple(
        CalendarSource(
            entity_id,
            _calendar_key(entity_id.split(".", 1)[1].replace("_", " ").title(), used_keys),
            entity_id.split(".", 1)[1].replace("_", " ").title(),
            colors[index % len(colors)],
        )
        for index, entity_id in enumerate(entity_ids)
    )


def load_calendar_settings():
    try:
        values = config.calendar_configuration()
        saved_calendars = home_entity_settings.runtime_entity_setting(
            "calendar_entities", None, db_path=config.DB_PATH
        )
        if saved_calendars is None:
            calendars = parse_calendar_sources(values["calendars"]) if values["calendars"] else ()
        else:
            calendars = calendar_sources_from_entities(saved_calendars)
    except (OSError, RuntimeError, ValueError) as exc:
        raise CalendarConfigurationError("Calendar configuration is invalid") from exc
    if not calendars:
        return None
    try:
        connection = load_home_assistant_connection()
    except HomeAssistantConfigurationError as exc:
        raise CalendarConfigurationError("Calendar configuration is invalid") from exc
    if connection is None:
        raise CalendarConfigurationError("Calendar configuration is incomplete")
    if values["stale_seconds"] < values["cache_seconds"]:
        raise CalendarConfigurationError("CALENDAR_STALE_SECONDS must be at least CALENDAR_CACHE_SECONDS")
    return CalendarSettings(
        connection=connection,
        calendars=calendars,
        lookahead_days=values["lookahead_days"],
        cache_seconds=values["cache_seconds"],
        stale_seconds=values["stale_seconds"],
        max_events=values["max_events"],
    )


def _local_timezone(now=None):
    if now is not None and now.tzinfo is not None:
        return now.tzinfo
    return datetime.now().astimezone().tzinfo or timezone.utc


def _normalized_now(now=None):
    current = now or datetime.now().astimezone()
    local_tz = _local_timezone(current)
    if current.tzinfo is None:
        current = current.replace(tzinfo=local_tz)
    return current.astimezone(local_tz), local_tz


def calendar_window(lookahead_days, now=None):
    current, local_tz = _normalized_now(now)
    start = datetime.combine(current.date(), datetime_time.min, tzinfo=local_tz)
    return start, start + timedelta(days=lookahead_days), current, local_tz


def _parse_datetime(value, local_tz):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(local_tz)


def _parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def normalize_event(raw_event, source, now, local_tz):
    if not isinstance(raw_event, dict):
        return None
    start_value = raw_event.get("start")
    end_value = raw_event.get("end")
    if not isinstance(start_value, dict) or not isinstance(end_value, dict):
        return None

    if "dateTime" in start_value or "dateTime" in end_value:
        start_dt = _parse_datetime(start_value.get("dateTime"), local_tz)
        end_dt = _parse_datetime(end_value.get("dateTime"), local_tz)
        if start_dt is None or end_dt is None or end_dt <= start_dt:
            return None
        start = start_dt.isoformat(timespec="seconds")
        end = end_dt.isoformat(timespec="seconds")
        all_day = False
        ongoing = start_dt <= now < end_dt
    elif "date" in start_value or "date" in end_value:
        start_date = _parse_date(start_value.get("date"))
        end_date = _parse_date(end_value.get("date"))
        if start_date is None or end_date is None or end_date <= start_date:
            return None
        start = start_date.isoformat()
        end = end_date.isoformat()
        all_day = True
        ongoing = start_date <= now.date() < end_date
    else:
        return None

    title = " ".join(str(raw_event.get("summary") or "").split()) or "Aftale"
    title = title[:MAX_TITLE_LENGTH]
    return {
        "calendar": {"key": source.key, "label": source.label, "color": source.color},
        "title": title,
        "start": start,
        "end": end,
        "all_day": all_day,
        "ongoing": ongoing,
    }


def _event_start_datetime(event, local_tz):
    if event["all_day"]:
        parsed = date.fromisoformat(event["start"])
        return datetime.combine(parsed, datetime_time.min, tzinfo=local_tz)
    parsed = datetime.fromisoformat(event["start"])
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(local_tz)


def _event_end_datetime(event, local_tz):
    if event["all_day"]:
        parsed = date.fromisoformat(event["end"])
        return datetime.combine(parsed, datetime_time.min, tzinfo=local_tz)
    parsed = datetime.fromisoformat(event["end"])
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=local_tz)
    return parsed.astimezone(local_tz)


def _event_sort_key(event, local_tz):
    return (
        _event_start_datetime(event, local_tz).astimezone(timezone.utc),
        0 if event["all_day"] else 1,
        _event_end_datetime(event, local_tz).astimezone(timezone.utc),
        event["calendar"]["key"],
        event["title"].casefold(),
    )


class HomeAssistantCalendarClient:
    def __init__(self, settings, client_factory: Callable = httpx.Client):
        self.settings = settings
        self.client_factory = client_factory

    def fetch(self, now=None):
        start, end, current, local_tz = calendar_window(self.settings.lookahead_days, now)
        client = HomeAssistantClient(self.settings.connection, self.client_factory)
        events = []
        failures = 0
        for source in self.settings.calendars:
            try:
                payload = client.get_json(
                    f"/api/calendars/{quote(source.entity_id, safe='')}",
                    params={"start": start.isoformat(), "end": end.isoformat()},
                )
            except HomeAssistantUnavailable:
                failures += 1
                continue
            if not isinstance(payload, list):
                failures += 1
                continue
            for raw_event in payload:
                normalized = normalize_event(raw_event, source, current, local_tz)
                if normalized is not None:
                    events.append(normalized)
        events.sort(key=lambda event: _event_sort_key(event, local_tz))
        return events[: self.settings.max_events], failures, current, local_tz


def _event_occurs_today(event, now, local_tz):
    day_start = datetime.combine(now.date(), datetime_time.min, tzinfo=local_tz)
    day_end = day_start + timedelta(days=1)
    return _event_start_datetime(event, local_tz) < day_end and _event_end_datetime(event, local_tz) > day_start


def _next_event_start(events, now, local_tz):
    for event in events:
        if _event_end_datetime(event, local_tz) > now:
            return event["start"]
    return None


def _empty_snapshot(status, calendars=(), unavailable_calendars=0):
    return {
        "status": status,
        "today_count": 0,
        "upcoming_count": 0,
        "next_event_start": None,
        "events": [],
        "calendars": [
            {"key": item.key, "label": item.label, "color": item.color}
            for item in calendars
        ],
        "unavailable_calendars": unavailable_calendars,
        "stale": False,
    }


def _snapshot(status, settings, events, failures, now, local_tz):
    return {
        "status": status,
        "today_count": sum(_event_occurs_today(event, now, local_tz) for event in events),
        "upcoming_count": len(events),
        "next_event_start": _next_event_start(events, now, local_tz),
        "events": copy.deepcopy(events),
        "calendars": [
            {"key": item.key, "label": item.label, "color": item.color}
            for item in settings.calendars
        ],
        "unavailable_calendars": failures,
        "stale": False,
    }


def _public_snapshot(snapshot, current_user):
    authenticated = (
        isinstance(current_user, dict)
        and current_user.get("role") in AUTHENTICATED_ROLES
    )
    result = copy.deepcopy(snapshot)
    if not authenticated:
        result["events"] = []
        result["calendars"] = []
    return result


class CalendarService:
    def __init__(
        self,
        settings_loader=load_calendar_settings,
        client_factory=httpx.Client,
        monotonic=time.monotonic,
        now_provider=lambda: datetime.now().astimezone(),
    ):
        self.settings_loader = settings_loader
        self.client_factory = client_factory
        self.monotonic = monotonic
        self.now_provider = now_provider
        self._lock = threading.Lock()
        self._cached = None
        self._cached_at = None
        self._signature = None

    def clear_cache(self):
        with self._lock:
            self._cached = None
            self._cached_at = None
            self._signature = None

    def get_calendar(self, current_user=None):
        if family_feature_hidden(current_user, "calendar"):
            return _empty_snapshot("hidden")
        try:
            settings = self.settings_loader()
        except CalendarConfigurationError:
            return _public_snapshot(_empty_snapshot("unavailable"), current_user)
        if settings is None:
            return _public_snapshot(_empty_snapshot("not_configured"), current_user)
        now_value = self.now_provider()
        signature = settings.signature()
        current_monotonic = self.monotonic()
        with self._lock:
            if self._signature != signature:
                self._cached = None
                self._cached_at = None
                self._signature = signature
            if self._cached is not None and self._cached_at is not None:
                age = max(0.0, current_monotonic - self._cached_at)
                if age < settings.cache_seconds:
                    return _public_snapshot(self._cached, current_user)
            events, failures, current, local_tz = HomeAssistantCalendarClient(
                settings, self.client_factory
            ).fetch(now_value)
            if failures < len(settings.calendars):
                status = "partial" if failures else "ok"
                snapshot = _snapshot(status, settings, events, failures, current, local_tz)
                self._cached = copy.deepcopy(snapshot)
                self._cached_at = current_monotonic
                return _public_snapshot(snapshot, current_user)
            if self._cached is not None and self._cached_at is not None:
                age = max(0.0, current_monotonic - self._cached_at)
                if age < settings.stale_seconds:
                    stale = copy.deepcopy(self._cached)
                    stale["status"] = "stale"
                    stale["stale"] = True
                    stale["unavailable_calendars"] = len(settings.calendars)
                    return _public_snapshot(stale, current_user)
            unavailable = _empty_snapshot(
                "unavailable", settings.calendars, len(settings.calendars)
            )
            return _public_snapshot(unavailable, current_user)


calendar_service = CalendarService()
router = APIRouter()


@router.get("/api/family/calendar")
def family_calendar(request: Request):
    current_user = getattr(request.state, "current_user", None)
    return calendar_service.get_calendar(current_user)
