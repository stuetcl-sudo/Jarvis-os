"""Adult-managed medication plans with bounded shared daily check-off."""
import json
from uuid import uuid4
from contextlib import closing
from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db import connect
from app.pets import adult_reader, editor, board_editor, today, family

router = APIRouter(prefix="/api/family/medication", tags=["medication"])


def initialize_medication(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS medication_plans (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, plan TEXT NOT NULL, revision TEXT NOT NULL DEFAULT '')")
    conn.execute("""CREATE TABLE IF NOT EXISTS medication_records (
        plan_id INTEGER NOT NULL, day TEXT NOT NULL, slot TEXT NOT NULL,
        status TEXT NOT NULL, recorded_at TEXT NOT NULL, recorded_by TEXT NOT NULL,
        plan_snapshot TEXT NOT NULL DEFAULT '{}', PRIMARY KEY(plan_id,day,slot))""")

    for table, column, definition in [("medication_plans", "revision", "TEXT NOT NULL DEFAULT ''"), ("medication_records", "plan_snapshot", "TEXT NOT NULL DEFAULT '{}' ")]:
        if column not in {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    user_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    instructions: str = Field(default="", max_length=1000)
    start_date: date
    end_date: date | None = None
    times: list[str] = Field(min_length=1, max_length=12)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7)
    active: bool = True

    @field_validator("times")
    @classmethod
    def valid_times(cls, value):
        import re
        if len(set(value)) != len(value) or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", t) for t in value):
            raise ValueError("Brug forskellige klokkeslæt i formatet HH:MM")
        return sorted(value)

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value):
        if len(set(value)) != len(value) or any(v < 0 or v > 6 for v in value):
            raise ValueError("Ugyldige ugedage")
        return sorted(value)

    @model_validator(mode="after")
    def valid_dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("Slutdato må ikke være før startdato")
        return self


class EditPlan(Plan):
    revision: str


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str
    day: date
    slot: str
    status: Literal["taken", "skipped", "unmarked"]


class DisplayRecord(Record):
    status: Literal["taken", "unmarked"]


def require_person(conn, user_id):
    if not conn.execute("SELECT 1 FROM auth_users WHERE user_id=? AND disabled=0 AND role IN ('owner','adult','child')", (user_id,)).fetchone():
        raise HTTPException(422, "Vælg et aktivt familiemedlem")


def get_plan(conn, plan_id):
    row = conn.execute("SELECT * FROM medication_plans WHERE id=?", (plan_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Medicinplanen findes ikke")
    return {**json.loads(row["plan"]), "revision": row["revision"]}


def scheduled(plan, day):
    return plan["active"] and plan["start_date"] <= day.isoformat() and (not plan["end_date"] or plan["end_date"] >= day.isoformat()) and day.weekday() in plan["weekdays"]


@router.get("")
def plans(user=Depends(adult_reader)):
    day = today()
    with closing(connect()) as conn:
        people = [dict(r) for r in conn.execute("SELECT user_id,display_name,role FROM auth_users WHERE disabled=0 AND role IN ('owner','adult','child') ORDER BY display_name")]
        eligible = {p["user_id"] for p in people}
        result = []
        for row in conn.execute("SELECT * FROM medication_plans ORDER BY id"):
            if row["user_id"] not in eligible:
                continue
            plan = {"id":row["id"], "revision":row["revision"], **json.loads(row["plan"])}
            plan["due_today"] = scheduled(plan,day)
            plan["records"] = [dict(r) for r in conn.execute("SELECT day,slot,status,recorded_at,recorded_by,plan_snapshot FROM medication_records WHERE plan_id=? AND day>=? AND day<=? ORDER BY day DESC,slot", (row["id"], date.fromordinal(max(1,day.toordinal()-29)).isoformat(),day.isoformat()))]
            result.append(plan)
    return {"today":day.isoformat(), "people":people, "plans":result}


def display_reader(user=Depends(family)):
    if user["role"] not in {"owner", "adult", "wall_display"}:
        raise HTTPException(403, "Medication display role required")
    return user


@router.get("/display")
def daily_display(user=Depends(display_reader)):
    """Shared display projection: today's names, times and status only."""
    day = today()
    entries = []
    with closing(connect()) as conn:
        people = [dict(r) for r in conn.execute("SELECT user_id,display_name FROM auth_users WHERE disabled=0 AND role IN ('owner','adult','child') ORDER BY display_name")]
        eligible = {p["user_id"]: p["display_name"] for p in people}
        for row in conn.execute("SELECT id,user_id,plan,revision FROM medication_plans ORDER BY id"):
            if row["user_id"] not in eligible:
                continue
            plan = json.loads(row["plan"])
            if not scheduled(plan, day):
                continue
            records = {r["slot"]: r["status"] for r in conn.execute("SELECT slot,status FROM medication_records WHERE plan_id=? AND day=?", (row["id"], day.isoformat()))}
            for slot in plan["times"]:
                entries.append({"id": f'{row["id"]}:{slot}', "plan_id":row["id"], "revision":row["revision"], "user_id": row["user_id"], "person": eligible[row["user_id"]], "name": plan["name"], "time": slot, "status": records.get(slot, "unmarked"), "read_only": False})
    entries.sort(key=lambda entry: (entry["time"], entry["id"]))
    return {"today": day.isoformat(), "people": people, "entries": entries}


@router.put("/display/{plan_id}/record")
def record_display(plan_id: int, payload: DisplayRecord, user=Depends(board_editor)):
    """Only today's prescribed slot; never edit a plan or mark it skipped."""
    return record(plan_id, payload, user)


@router.post("", status_code=201)
def create_plan(payload: Plan, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        require_person(conn,payload.user_id)
        if conn.execute("SELECT COUNT(*) FROM medication_plans").fetchone()[0] >= 200:
            raise HTTPException(409, "Der kan højst oprettes 200 planer")
        result = conn.execute("INSERT INTO medication_plans(user_id,plan,revision) VALUES (?,?,?)", (payload.user_id,payload.model_dump_json(),uuid4().hex))
        return {"id":result.lastrowid}


@router.put("/{plan_id}")
def edit_plan(plan_id: int, payload: EditPlan, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        old = get_plan(conn,plan_id)
        if old["revision"] != payload.revision:
            raise HTTPException(409, "Planen er ændret. Opdater siden og prøv igen.")
        if old["user_id"] != payload.user_id:
            raise HTTPException(422, "Opret en ny plan for en anden person")
        require_person(conn,payload.user_id)
        conn.execute("UPDATE medication_plans SET plan=?,revision=? WHERE id=?", (payload.model_dump_json(exclude={"revision"}),uuid4().hex,plan_id))
    return {"ok":True}


@router.put("/{plan_id}/record")
def record(plan_id: int, payload: Record, user=Depends(editor)):
    if payload.day != today():
        raise HTTPException(409, "Registrér kun i dag. Opdater siden efter midnat.")
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        plan = get_plan(conn,plan_id)
        require_person(conn,plan["user_id"])
        if payload.revision != plan["revision"]:
            raise HTTPException(409, "Planen er ændret. Opdater siden før registrering.")
        if not scheduled(plan,payload.day) or payload.slot not in plan["times"]:
            raise HTTPException(409, "Tidspunktet findes ikke i dagens aktive plan")
        if payload.status == "unmarked":
            conn.execute("DELETE FROM medication_records WHERE plan_id=? AND day=? AND slot=?", (plan_id,payload.day.isoformat(),payload.slot))
        else:
            conn.execute("INSERT INTO medication_records VALUES (?,?,?,?,?,?,?) ON CONFLICT(plan_id,day,slot) DO UPDATE SET status=excluded.status,recorded_at=excluded.recorded_at,recorded_by=excluded.recorded_by,plan_snapshot=excluded.plan_snapshot", (plan_id,payload.day.isoformat(),payload.slot,payload.status,datetime.now().astimezone().isoformat(),user["user_id"],json.dumps({"name":plan["name"],"instructions":plan["instructions"]},ensure_ascii=False)))
    return {"ok":True}


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, user=Depends(editor)):
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        get_plan(conn,plan_id)
        conn.execute("DELETE FROM medication_records WHERE plan_id=?", (plan_id,))
        conn.execute("DELETE FROM medication_plans WHERE id=?", (plan_id,))
    return {"ok":True}
