"""Local family plans. Calendar and Home Assistant meals remain read-only sources."""
from contextlib import closing
from datetime import date, timedelta
import json
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.db import connect
from app.pets import family, editor, today
from app.shopping import require_list

router = APIRouter(prefix="/api/family/planning", tags=["family-planning"])


def initialize_family_planning(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS family_plans (day TEXT PRIMARY KEY, payload TEXT NOT NULL)")


class DayPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    meal: str = Field(default="", max_length=160)
    recipe_url: str = Field(default="", max_length=1000)
    cook: str = Field(default="", max_length=80)
    ingredients: list[str] = Field(default_factory=list, max_length=60)
    meal_notes: str = Field(default="", max_length=500)
    pickup: str = Field(default="", max_length=80)
    pickup_time: str = Field(default="", pattern=r"^(?:|(?:[01]\d|2[0-3]):[0-5]\d)$")
    pickup_notes: str = Field(default="", max_length=500)
    reminders: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("recipe_url")
    @classmethod
    def safe_recipe(cls, value):
        if value:
            try:
                url = urlsplit(value)
                if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password or any(c.isspace() for c in value):
                    raise ValueError("Brug et almindeligt http- eller https-link til opskriften")
                _ = url.port
            except ValueError:
                raise ValueError("Brug et almindeligt http- eller https-link til opskriften")
        return value

    @field_validator("ingredients", "reminders")
    @classmethod
    def tidy_lines(cls, values):
        result = []
        for value in values:
            value = value.strip()
            if not value or len(value) > 160:
                raise ValueError("Hver linje skal indeholde 1–160 tegn")
            if value.casefold() not in {item.casefold() for item in result}:
                result.append(value)
        return result


class ShoppingTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_id: int = Field(gt=0)


@router.get("")
def read_week(start: date | None = None, user=Depends(family)):
    start = start or today()
    if start > date.max - timedelta(days=6):
        raise HTTPException(422, "Datoen er uden for kalenderen")
    with closing(connect()) as conn:
        plans = {row["day"]: json.loads(row["payload"]) for row in conn.execute(
            "SELECT * FROM family_plans WHERE day BETWEEN ? AND ?", (start.isoformat(), (start + timedelta(days=6)).isoformat()))}
        people = [row[0] for row in conn.execute("SELECT display_name FROM auth_users WHERE disabled=0 AND role IN ('owner','adult','child') ORDER BY display_name")]
    return {"today": today().isoformat(), "can_edit": user["role"] in {"owner", "adult"}, "people": people,
            "days": [{"date": (start + timedelta(days=i)).isoformat(), **plans.get((start + timedelta(days=i)).isoformat(), DayPlan().model_dump())} for i in range(7)]}


@router.put("/{day}")
def save_day(day: date, payload: DayPlan, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute("INSERT INTO family_plans(day,payload) VALUES (?,?) ON CONFLICT(day) DO UPDATE SET payload=excluded.payload",
                     (day.isoformat(), json.dumps(payload.model_dump(), ensure_ascii=False)))
    return {"ok": True}


@router.post("/{day}/shopping")
def send_ingredients(day: date, payload: ShoppingTarget, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        require_list(conn, payload.list_id)
        row = conn.execute("SELECT payload FROM family_plans WHERE day=?", (day.isoformat(),)).fetchone()
        if not row:
            raise HTTPException(404, "Gem dagens ingredienser først")
        plan = json.loads(row[0])
        existing = {row[0].strip().casefold() for row in conn.execute("SELECT name FROM shopping_items WHERE list_id=? AND done=0", (payload.list_id,))}
        additions = [name for name in plan["ingredients"] if name.casefold() not in existing]
        count = conn.execute("SELECT COUNT(*) FROM shopping_items WHERE list_id=?", (payload.list_id,)).fetchone()[0]
        if count + len(additions) > 500:
            raise HTTPException(409, "Listen kan højst indeholde 500 varer")
        for name in additions:
            conn.execute("INSERT INTO shopping_items(list_id,name,quantity,category,note) VALUES (?,?,?,?,?)",
                         (payload.list_id, name, "", "Madplan", f'{day.isoformat()} · {plan["meal"]}'[:320]))
    return {"added": len(additions), "already_present": len(plan["ingredients"]) - len(additions)}
