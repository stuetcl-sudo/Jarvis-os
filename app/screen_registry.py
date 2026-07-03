import re
import sqlite3
from datetime import datetime, timezone

from app import config

SCREEN_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
SCREEN_TYPES = {"wall-large", "wall-tablet", "wall-square", "mobile"}
SCREEN_MODULES = {"routine", "calendar", "weather", "meal", "tasks", "home", "system"}
DEFAULT_MODULES = ["routine", "calendar", "weather", "meal", "tasks", "home"]
DEFAULT_SCREEN = {
    "name": "Vægskærm",
    "slug": "wall",
    "screen_type": "wall-large",
    "modules": DEFAULT_MODULES,
    "is_active": True,
}

SCREEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS screens (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    screen_type TEXT NOT NULL,
    modules TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def connect():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_screen_table(conn):
    conn.execute(SCREEN_SCHEMA)


def normalize_slug(value):
    slug = str(value or "").strip().lower().replace("_", "-")
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if not slug or not SCREEN_SLUG_RE.fullmatch(slug):
        raise ValueError("screen slug is invalid")
    return slug


def normalize_modules(values):
    if values is None:
        return list(DEFAULT_MODULES)
    modules = []
    for value in values:
        key = str(value or "").strip().lower()
        if key in SCREEN_MODULES and key not in modules:
            modules.append(key)
    if not modules:
        raise ValueError("screen must have at least one module")
    return modules


def normalize_screen_type(value):
    screen_type = str(value or "wall-large").strip().lower()
    if screen_type not in SCREEN_TYPES:
        raise ValueError("screen type is invalid")
    return screen_type


def serialize_modules(modules):
    return ",".join(modules)


def parse_modules(value):
    return [item for item in str(value or "").split(",") if item]


def row_to_screen(row):
    if not row:
        return None
    item = dict(row)
    item["modules"] = parse_modules(item.get("modules"))
    item["is_active"] = bool(item.get("is_active"))
    item["url"] = "/wall" if item["slug"] == "wall" else f"/wall/{item['slug']}"
    return item


def default_screen():
    return {**DEFAULT_SCREEN, "url": "/wall"}


def get_screen(slug="wall"):
    slug = normalize_slug(slug or "wall")
    if slug == "wall":
        fallback = default_screen()
    else:
        fallback = None
    conn = connect()
    try:
        ensure_screen_table(conn)
        row = conn.execute("SELECT * FROM screens WHERE slug = ?", (slug,)).fetchone()
        screen = row_to_screen(row)
        return screen or fallback
    finally:
        conn.close()


def list_screens():
    conn = connect()
    try:
        ensure_screen_table(conn)
        rows = conn.execute("SELECT * FROM screens ORDER BY slug ASC").fetchall()
        screens = [row_to_screen(row) for row in rows]
        if not any(item["slug"] == "wall" for item in screens):
            screens.insert(0, default_screen())
        return screens
    finally:
        conn.close()


def upsert_screen(name, slug, screen_type="wall-large", modules=None, is_active=True):
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        raise ValueError("screen name is required")
    slug = normalize_slug(slug)
    screen_type = normalize_screen_type(screen_type)
    modules = normalize_modules(modules)
    timestamp = now_iso()
    conn = connect()
    try:
        ensure_screen_table(conn)
        existing = conn.execute("SELECT slug FROM screens WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE screens SET name = ?, screen_type = ?, modules = ?, is_active = ?, updated_at = ? WHERE slug = ?",
                (cleaned_name, screen_type, serialize_modules(modules), 1 if is_active else 0, timestamp, slug),
            )
        else:
            conn.execute(
                "INSERT INTO screens (slug, name, screen_type, modules, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (slug, cleaned_name, screen_type, serialize_modules(modules), 1 if is_active else 0, timestamp, timestamp),
            )
        conn.commit()
    finally:
        conn.close()
    return get_screen(slug)


def delete_screen(slug):
    slug = normalize_slug(slug)
    if slug == "wall":
        raise ValueError("default screen cannot be deleted")
    conn = connect()
    try:
        ensure_screen_table(conn)
        conn.execute("DELETE FROM screens WHERE slug = ?", (slug,))
        conn.commit()
    finally:
        conn.close()
