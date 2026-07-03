import json
import re
import sqlite3
from datetime import datetime, timezone

from app import config

SCREEN_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
SCREEN_TYPES = {"wall-large", "wall-tablet", "wall-square", "mobile"}
SCREEN_MODULES = {"routine", "calendar", "weather", "meal", "tasks", "home", "system"}
SCREEN_MODULE_SIZES = {"small", "medium", "large", "wide", "full"}
DEFAULT_MODULES = ["routine", "calendar", "weather", "meal", "tasks", "home"]
DEFAULT_MODULE_LAYOUT = {
    "routine": "large",
    "calendar": "full",
    "weather": "wide",
    "meal": "medium",
    "tasks": "wide",
    "home": "medium",
    "system": "medium",
}
LEGACY_DEFAULT_MODULE_LAYOUT = {
    "routine": "medium",
    "calendar": "wide",
    "weather": "medium",
    "meal": "medium",
    "tasks": "wide",
    "home": "medium",
}
DEFAULT_SCREEN = {
    "name": "Vægskærm",
    "slug": "wall",
    "screen_type": "wall-large",
    "modules": DEFAULT_MODULES,
    "module_layout": {module: DEFAULT_MODULE_LAYOUT[module] for module in DEFAULT_MODULES},
    "is_active": True,
}

SCREEN_SCHEMA = """
CREATE TABLE IF NOT EXISTS screens (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    screen_type TEXT NOT NULL,
    modules TEXT NOT NULL,
    module_layout TEXT NOT NULL DEFAULT '{}',
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
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(screens)").fetchall()}
    if "module_layout" not in columns:
        conn.execute("ALTER TABLE screens ADD COLUMN module_layout TEXT NOT NULL DEFAULT '{}'")


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


def normalize_module_layout(values, modules):
    source = values if isinstance(values, dict) else {}
    layout = {}
    for module in modules:
        supplied = source.get(module)
        size = str(supplied or DEFAULT_MODULE_LAYOUT.get(module, "medium")).strip().lower()
        if supplied is not None and size not in SCREEN_MODULE_SIZES:
            raise ValueError("module size is invalid")
        if size not in SCREEN_MODULE_SIZES:
            size = "medium"
        layout[module] = size
    return layout


def normalize_screen_type(value):
    screen_type = str(value or "wall-large").strip().lower()
    if screen_type not in SCREEN_TYPES:
        raise ValueError("screen type is invalid")
    return screen_type


def serialize_modules(modules):
    return ",".join(modules)


def parse_modules(value):
    return [item for item in str(value or "").split(",") if item]


def serialize_module_layout(layout):
    return json.dumps(layout or {}, sort_keys=True, separators=(",", ":"))


def parse_module_layout(value):
    try:
        parsed = json.loads(str(value or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def default_screen():
    return {**DEFAULT_SCREEN, "modules": list(DEFAULT_MODULES), "module_layout": dict(DEFAULT_SCREEN["module_layout"]), "url": "/wall"}


def row_to_screen(row):
    if not row:
        return None
    item = dict(row)
    item["modules"] = parse_modules(item.get("modules"))
    parsed_layout = parse_module_layout(item.get("module_layout"))
    if item.get("slug") == "wall" and item["modules"] == DEFAULT_MODULES and parsed_layout == LEGACY_DEFAULT_MODULE_LAYOUT:
        parsed_layout = DEFAULT_MODULE_LAYOUT
    item["module_layout"] = normalize_module_layout(parsed_layout, item["modules"])
    item["is_active"] = bool(item.get("is_active"))
    item["url"] = "/wall" if item["slug"] == "wall" else f"/wall/{item['slug']}"
    return item


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


def upsert_screen(name, slug, screen_type="wall-large", modules=None, is_active=True, module_layout=None):
    cleaned_name = str(name or "").strip()
    if not cleaned_name:
        raise ValueError("screen name is required")
    slug = normalize_slug(slug)
    screen_type = normalize_screen_type(screen_type)
    modules = normalize_modules(modules)
    module_layout = normalize_module_layout(module_layout, modules)
    timestamp = now_iso()
    conn = connect()
    try:
        ensure_screen_table(conn)
        existing = conn.execute("SELECT slug FROM screens WHERE slug = ?", (slug,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE screens SET name = ?, screen_type = ?, modules = ?, module_layout = ?, is_active = ?, updated_at = ? WHERE slug = ?",
                (cleaned_name, screen_type, serialize_modules(modules), serialize_module_layout(module_layout), 1 if is_active else 0, timestamp, slug),
            )
        else:
            conn.execute(
                "INSERT INTO screens (slug, name, screen_type, modules, module_layout, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (slug, cleaned_name, screen_type, serialize_modules(modules), serialize_module_layout(module_layout), 1 if is_active else 0, timestamp, timestamp),
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
