"""Local household pets. No external integrations or automated medical advice."""
import base64
import binascii
import json
from contextlib import closing
from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Literal
from uuid import UUID
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
    conn.execute("""CREATE TABLE IF NOT EXISTS pet_care_entries (
        id INTEGER PRIMARY KEY, pet_id INTEGER NOT NULL, day TEXT NOT NULL,
        task TEXT NOT NULL, request_id TEXT NOT NULL, completed_at TEXT NOT NULL,
        voided INTEGER NOT NULL DEFAULT 0, UNIQUE(pet_id,day,task,request_id))""")
    conn.execute("INSERT OR IGNORE INTO pet_care_entries(pet_id,day,task,request_id,completed_at) SELECT pet_id,day,task,'legacy',completed_at FROM pet_care")
    conn.execute("DELETE FROM pet_care")
    columns = {r[1] for r in conn.execute("PRAGMA table_info(pet_reminders)")}
    for name, definition in [("interval_unit", "TEXT NOT NULL DEFAULT 'none'"), ("interval_count", "INTEGER NOT NULL DEFAULT 1"), ("interval_anchor", "TEXT NOT NULL DEFAULT ''")]:
        if name not in columns:
            conn.execute(f"ALTER TABLE pet_reminders ADD COLUMN {name} {definition}")
    conn.execute("CREATE TABLE IF NOT EXISTS pet_reminder_history (reminder_id INTEGER NOT NULL, due_date TEXT NOT NULL, completed_at TEXT NOT NULL, PRIMARY KEY(reminder_id,due_date))")
    conn.execute("CREATE TABLE IF NOT EXISTS pet_expenses (id INTEGER PRIMARY KEY, pet_id INTEGER NOT NULL, day TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL, amount_ore INTEGER NOT NULL, notes TEXT NOT NULL)")


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
    vet_name: str = Field(default="", max_length=120)
    vet_clinic: str = Field(default="", max_length=160)
    vet_phone: str = Field(default="", max_length=40)
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
    interval_unit: Literal["none", "days", "weeks", "months", "years"] = "none"
    interval_count: int = Field(default=1, ge=1, le=365)


class ReminderState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    completed: bool
    occurrence_date: date | None = None


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
            entries = [dict(r) for r in conn.execute("SELECT id,task,completed_at FROM pet_care_entries WHERE pet_id=? AND day=? AND voided=0 ORDER BY id", (row["id"], day))]
            pet["care_entries"] = entries
            pet["care_counts"] = {task: sum(e["task"] == task for e in entries) for task in ("food", "water", "walk")}
            pet["care"] = {e["task"]: e["completed_at"] for e in entries}
            pet["reminders"] = [dict(r) for r in conn.execute(
                "SELECT id,title,kind,due_date,notes,completed,interval_unit,interval_count FROM pet_reminders WHERE pet_id=? ORDER BY completed,due_date,id", (row["id"],))]
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
        conn.execute("DELETE FROM pet_care_entries WHERE pet_id=?", (pet_id,))
        conn.execute("DELETE FROM pet_reminder_history WHERE reminder_id IN (SELECT id FROM pet_reminders WHERE pet_id=?)", (pet_id,))
        conn.execute("DELETE FROM pet_reminders WHERE pet_id=?", (pet_id,))
        conn.execute("DELETE FROM pet_expenses WHERE pet_id=?", (pet_id,))
        conn.execute("DELETE FROM pets WHERE id=?", (pet_id,))
    return {"ok": True}


@router.put("/{pet_id}/care/{task}")
def update_care(pet_id: int, task: Literal["food", "water", "walk"], payload: CareUpdate, user=Depends(carer)):
    if payload.day != today():
        raise HTTPException(409, "Dagen er skiftet. Opdater siden og prøv igen.")
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        if payload.done:
            conn.execute("""INSERT INTO pet_care_entries(pet_id,day,task,request_id,completed_at) VALUES (?,?,?,'legacy',?)
                ON CONFLICT(pet_id,day,task,request_id) DO UPDATE SET voided=0""", (pet_id,payload.day.isoformat(),task,datetime.now().astimezone().isoformat()))
        else:
            conn.execute("UPDATE pet_care_entries SET voided=1 WHERE pet_id=? AND day=? AND task=? AND request_id='legacy'", (pet_id,payload.day.isoformat(),task))
    return {"ok": True}


class CareEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: date
    request_id: UUID


@router.post("/{pet_id}/care/{task}/entries", status_code=201)
def add_care_entry(pet_id: int, task: Literal["food", "water", "walk"], payload: CareEntry, user=Depends(carer)):
    if payload.day != today():
        raise HTTPException(409, "Dagen er skiftet. Opdater siden og prøv igen.")
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        require_pet(conn,pet_id)
        existing = conn.execute("SELECT id FROM pet_care_entries WHERE pet_id=? AND day=? AND task=? AND request_id=?", (pet_id,payload.day.isoformat(),task,str(payload.request_id))).fetchone()
        if existing:
            return {"id":existing["id"]}
        if conn.execute("SELECT COUNT(*) FROM pet_care_entries WHERE pet_id=? AND day=?", (pet_id,payload.day.isoformat())).fetchone()[0] >= 300:
            raise HTTPException(409, "Der kan højst registreres 300 pasninger pr. dyr pr. dag")
        result = conn.execute("INSERT INTO pet_care_entries(pet_id,day,task,request_id,completed_at) VALUES (?,?,?,?,?)", (pet_id,payload.day.isoformat(),task,str(payload.request_id),datetime.now().astimezone().isoformat()))
        return {"id":result.lastrowid}


@router.delete("/{pet_id}/care/entries/{entry_id}")
def undo_care_entry(pet_id: int, entry_id: int, user=Depends(carer)):
    with closing(connect()) as conn, conn:
        row = conn.execute("SELECT day FROM pet_care_entries WHERE id=? AND pet_id=?", (entry_id,pet_id)).fetchone()
        if not row:
            raise HTTPException(404, "Registreringen findes ikke")
        if row["day"] != today().isoformat():
            raise HTTPException(409, "Kun dagens registreringer kan fortrydes")
        conn.execute("UPDATE pet_care_entries SET voided=1 WHERE id=?", (entry_id,))
    return {"ok":True}


@router.post("/{pet_id}/reminders", status_code=201)
def create_reminder(pet_id: int, payload: Reminder, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        if conn.execute("SELECT COUNT(*) FROM pet_reminders WHERE pet_id=?", (pet_id,)).fetchone()[0] >= 200:
            raise HTTPException(409, "Der kan højst gemmes 200 påmindelser pr. kæledyr")
        cursor = conn.execute("INSERT INTO pet_reminders(pet_id,title,kind,due_date,notes,interval_unit,interval_count,interval_anchor) VALUES (?,?,?,?,?,?,?,?)",
                              (pet_id, payload.title, payload.kind, payload.due_date.isoformat(), payload.notes, payload.interval_unit, payload.interval_count, payload.due_date.isoformat()))
        return {"id": cursor.lastrowid}


def next_due(day, unit, count, anchor=None):
    try:
        if unit in {"days", "weeks"}:
            return day + timedelta(days=count * (7 if unit == "weeks" else 1))
        months = count * (12 if unit == "years" else 1)
        index = day.year * 12 + day.month - 1 + months
        year, month = divmod(index, 12)
        return date(year, month + 1, min((anchor or day).day, monthrange(year, month + 1)[1]))
    except (ValueError, OverflowError):
        raise HTTPException(422, "Næste dato ligger uden for det understøttede interval")


@router.put("/{pet_id}/reminders/{reminder_id}")
def complete_reminder(pet_id: int, reminder_id: int, payload: ReminderState, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM pet_reminders WHERE id=? AND pet_id=?", (reminder_id,pet_id)).fetchone()
        if not row:
            raise HTTPException(404, "Påmindelsen findes ikke")
        if row["interval_unit"] != "none":
            if not payload.completed or payload.occurrence_date != date.fromisoformat(row["due_date"]):
                raise HTTPException(409, "Påmindelsen er ændret. Opdater siden og prøv igen.")
            following = next_due(payload.occurrence_date, row["interval_unit"], row["interval_count"], date.fromisoformat(row["interval_anchor"] or row["due_date"]))
            conn.execute("INSERT OR IGNORE INTO pet_reminder_history VALUES (?,?,?)", (reminder_id,row["due_date"],datetime.now().astimezone().isoformat()))
            conn.execute("UPDATE pet_reminders SET due_date=?,completed=0 WHERE id=?", (following.isoformat(),reminder_id))
        else:
            conn.execute("UPDATE pet_reminders SET completed=? WHERE id=?", (payload.completed,reminder_id))
    return {"ok": True}


@router.delete("/{pet_id}/reminders/{reminder_id}")
def delete_reminder(pet_id: int, reminder_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor = conn.execute("DELETE FROM pet_reminders WHERE id=? AND pet_id=?", (reminder_id, pet_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Påmindelsen findes ikke")
        conn.execute("DELETE FROM pet_reminder_history WHERE reminder_id=?", (reminder_id,))
    return {"ok": True}


@router.patch("/{pet_id}/reminders/{reminder_id}")
def edit_reminder(pet_id: int, reminder_id: int, payload: Reminder, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        cursor = conn.execute(
            "UPDATE pet_reminders SET title=?,kind=?,due_date=?,notes=?,interval_unit=?,interval_count=?,interval_anchor=?,completed=CASE WHEN due_date=? AND interval_unit=? AND interval_count=? THEN completed ELSE 0 END WHERE id=? AND pet_id=?",
            (payload.title, payload.kind, payload.due_date.isoformat(), payload.notes, payload.interval_unit, payload.interval_count, payload.due_date.isoformat(), payload.due_date.isoformat(), payload.interval_unit, payload.interval_count, reminder_id, pet_id))
        if not cursor.rowcount:
            raise HTTPException(404, "Påmindelsen findes ikke")
    return {"ok": True}


class Expense(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    day: date
    category: Literal["food", "vet", "medicine", "insurance", "care", "other"]
    title: str = Field(min_length=1, max_length=160)
    amount_ore: int = Field(gt=0, le=100000000, strict=True)
    notes: str = Field(default="", max_length=1000)

    @field_validator("day")
    @classmethod
    def actual_day(cls, value):
        if value > today():
            raise ValueError("Registrér kun afholdte udgifter")
        return value


def adult_reader(user=Depends(family)):
    if user["role"] not in {"owner", "adult"}:
        raise HTTPException(403, "Adult role required")
    return user


@router.get("/{pet_id}/expenses")
def expenses(pet_id: int, user=Depends(adult_reader)):
    with closing(connect()) as conn:
        require_pet(conn, pet_id)
        return {"currency": "DKK", "expenses": [dict(r) for r in conn.execute("SELECT * FROM pet_expenses WHERE pet_id=? ORDER BY day DESC,id DESC", (pet_id,))]}


@router.post("/{pet_id}/expenses", status_code=201)
def create_expense(pet_id: int, payload: Expense, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        require_pet(conn, pet_id)
        if conn.execute("SELECT COUNT(*) FROM pet_expenses WHERE pet_id=?", (pet_id,)).fetchone()[0] >= 5000:
            raise HTTPException(409, "Der kan højst gemmes 5000 udgifter pr. dyr")
        result = conn.execute("INSERT INTO pet_expenses(pet_id,day,category,title,amount_ore,notes) VALUES (?,?,?,?,?,?)", (pet_id,payload.day.isoformat(),payload.category,payload.title,payload.amount_ore,payload.notes))
        return {"id": result.lastrowid}


@router.delete("/{pet_id}/expenses/{expense_id}")
def delete_expense(pet_id: int, expense_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        if not conn.execute("DELETE FROM pet_expenses WHERE id=? AND pet_id=?", (expense_id,pet_id)).rowcount:
            raise HTTPException(404, "Udgiften findes ikke")
    return {"ok": True}
