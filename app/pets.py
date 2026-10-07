"""Local household pets. No external integrations or automated medical advice."""
import base64
import binascii
import json
from contextlib import closing
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app import config
from app.auth.dependencies import require_authenticated_user, require_csrf
from app.db import connect
from app.home_setup import load_home_settings

router = APIRouter(prefix="/api/family/pets", tags=["pets"])
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS pets (id INTEGER PRIMARY KEY, profile TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS pet_care (
        pet_id INTEGER NOT NULL, day TEXT NOT NULL, task TEXT NOT NULL,
        completed_at TEXT NOT NULL, PRIMARY KEY(pet_id, day, task))""",
    """CREATE TABLE IF NOT EXISTS pet_reminders (
        id INTEGER PRIMARY KEY, pet_id INTEGER NOT NULL, title TEXT NOT NULL,
        kind TEXT NOT NULL, due_date TEXT NOT NULL, notes TEXT NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0)""",
)


def initialize_pets(conn):
    for statement in SCHEMA:
        conn.execute(statement)


def today():
    return datetime.now(ZoneInfo(load_home_settings(db_path=config.DB_PATH)["timezone"])).date()


def family(user=Depends(require_authenticated_user)):
    if user["role"] not in {"owner", "adult", "child", "wall_display"}:
        raise HTTPException(403, "Family role required")
    return user


def carer(user=Depends(require_csrf)):
    if user["role"] not in {"owner", "adult", "child"}:
        raise HTTPException(403, "Family member required")
    return user


def editor(user=Depends(require_csrf)):
    if user["role"] not in {"owner", "adult"}:
        raise HTTPException(403, "Adult role required")
    return user


class PetProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    breed: str = Field(default="", max_length=120)
    birth_date: date | None = None
    chip_number: str = Field(default="", max_length=40)
    weight_kg: float | None = Field(default=None, gt=0, le=1500, allow_inf_nan=False)
    photo: str = Field(default="", max_length=400000)

    @field_validator("birth_date")
    @classmethod
    def past_birth(cls, value):
        if value and value > today():
            raise ValueError("Fødselsdato må ikke ligge i fremtiden")
        return value

    @field_validator("photo")
    @classmethod
    def safe_photo(cls, value):
        if not value:
            return value
        try:
            header, encoded = value.split(",", 1)
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Ugyldigt billede") from exc
        if not ((header == "data:image/jpeg;base64" and raw.startswith(b"\xff\xd8\xff")) or
                (header == "data:image/png;base64" and raw.startswith(b"\x89PNG\r\n\x1a\n"))):
            raise ValueError("Brug et JPEG- eller PNG-billede")
        return value


class CareUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done: bool
    day: date  # Avoid completing yesterday's displayed task after midnight.


class Reminder(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["vaccination", "medicine", "vet", "other"]
    due_date: date
    notes: str = Field(default="", max_length=1000)


class ReminderState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed: bool


def require_pet(conn, pet_id):
    if not conn.execute("SELECT id FROM pets WHERE id=?", (pet_id,)).fetchone():
        raise HTTPException(404, "Kæledyret findes ikke")


@router.get("")
def list_pets(user=Depends(family)):
    day = today().isoformat()
    with closing(connect()) as conn:
        pets = []
        for row in conn.execute("SELECT * FROM pets ORDER BY id"):
            pet = {"id": row["id"], **json.loads(row["profile"])}
            pet["care"] = {r["task"]: r["completed_at"] for r in conn.execute(
                "SELECT task, completed_at FROM pet_care WHERE pet_id=? AND day=?", (row["id"], day))}
            pet["reminders"] = [dict(r) for r in conn.execute(
                "SELECT id,title,kind,due_date,notes,completed FROM pet_reminders WHERE pet_id=? ORDER BY completed,due_date,id", (row["id"],))]
            pets.append(pet)
    return {"pets": pets, "today": day, "can_edit": user["role"] in {"owner", "adult"},
            "can_care": user["role"] in {"owner", "adult", "child"}}


@router.post("", status_code=201)
def create_pet(payload: PetProfile, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        if conn.execute("SELECT COUNT(*) FROM pets").fetchone()[0] >= 30:
            raise HTTPException(409, "Der kan højst oprettes 30 kæledyr")
        cursor = conn.execute("INSERT INTO pets(profile) VALUES (?)", (payload.model_dump_json(),))
        return {"id": cursor.lastrowid}


@router.put("/{pet_id}")
def update_pet(pet_id: int, payload: PetProfile, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        conn.execute("UPDATE pets SET profile=? WHERE id=?", (payload.model_dump_json(), pet_id))
    return {"ok": True}


@router.delete("/{pet_id}")
def delete_pet(pet_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        conn.execute("DELETE FROM pet_care WHERE pet_id=?", (pet_id,))
        conn.execute("DELETE FROM pet_reminders WHERE pet_id=?", (pet_id,))
        conn.execute("DELETE FROM pets WHERE id=?", (pet_id,))
    return {"ok": True}


@router.put("/{pet_id}/care/{task}")
def update_care(pet_id: int, task: Literal["food", "water", "walk"], payload: CareUpdate, user=Depends(carer)):
    if payload.day != today():
        raise HTTPException(409, "Dagen er skiftet. Opdater siden og prøv igen.")
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        if payload.done:
            conn.execute("INSERT OR IGNORE INTO pet_care VALUES (?,?,?,?)", (
                pet_id, payload.day.isoformat(), task, datetime.now().astimezone().isoformat()))
        else:
            conn.execute("DELETE FROM pet_care WHERE pet_id=? AND day=? AND task=?", (pet_id, payload.day.isoformat(), task))
    return {"ok": True}


@router.post("/{pet_id}/reminders", status_code=201)
def create_reminder(pet_id: int, payload: Reminder, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        if conn.execute("SELECT COUNT(*) FROM pet_reminders WHERE pet_id=?", (pet_id,)).fetchone()[0] >= 200:
            raise HTTPException(409, "Der kan højst gemmes 200 påmindelser pr. kæledyr")
        cursor = conn.execute("INSERT INTO pet_reminders(pet_id,title,kind,due_date,notes) VALUES (?,?,?,?,?)",
                              (pet_id, payload.title, payload.kind, payload.due_date.isoformat(), payload.notes))
        return {"id": cursor.lastrowid}


@router.put("/{pet_id}/reminders/{reminder_id}")
def complete_reminder(pet_id: int, reminder_id: int, payload: ReminderState, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor = conn.execute("UPDATE pet_reminders SET completed=? WHERE id=? AND pet_id=?", (payload.completed, reminder_id, pet_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Påmindelsen findes ikke")
    return {"ok": True}


@router.delete("/{pet_id}/reminders/{reminder_id}")
def delete_reminder(pet_id: int, reminder_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor = conn.execute("DELETE FROM pet_reminders WHERE id=? AND pet_id=?", (reminder_id, pet_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Påmindelsen findes ikke")
    return {"ok": True}


@router.patch("/{pet_id}/reminders/{reminder_id}")
def edit_reminder(pet_id: int, reminder_id: int, payload: Reminder, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor = conn.execute(
            "UPDATE pet_reminders SET title=?,kind=?,due_date=?,notes=? WHERE id=? AND pet_id=?",
            (payload.title, payload.kind, payload.due_date.isoformat(), payload.notes, reminder_id, pet_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Påmindelsen findes ikke")
    return {"ok": True}
