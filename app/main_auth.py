import hmac

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import config
from app.auth.context import reset_current_actor, set_current_actor
from app.auth.routes import router as auth_router
from app.auth.service import SESSION_COOKIE_NAME, auth_service
from app.bootstrap_routes import router as bootstrap_router
from app.calendar import router as calendar_router
from app.db import log_action
from app.family_tasks import router as family_tasks_router
from app.family_view import render_family_page
from app.family_visibility import family_feature_hidden, router as family_visibility_router
from app.health import get_health
from app.main import app
from app.meal_plan import router as meal_plan_router
from app.module_settings import router as module_settings_router
from app.routine_definitions import EDITOR_ROLES
from app.routines import ROUTINE_ROLES, router as routines_router
from app.safety_status import status_item
from app.safety_status import router as safety_status_router
from app.screen_routes import router as screen_router
from app.setup_state import BOOTSTRAP_REQUIRED, READY, setup_status
from app.wall_view import WALL_ROLES, render_wall_page
from app.weather import router as weather_router

app.include_router(auth_router)
app.include_router(bootstrap_router)
app.include_router(weather_router)
app.include_router(calendar_router)
app.include_router(meal_plan_router)
app.include_router(family_tasks_router)
app.include_router(routines_router)
app.include_router(safety_status_router)
app.include_router(family_visibility_router)
app.include_router(module_settings_router)
app.include_router(screen_router)

ROUTINE_WRITE_ACTIONS = {"complete", "back", "reset"}
OWNER_DOCUMENTATION_PATHS = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}


def wall_login_target(path):
    return f"/login?next={path}"


def is_owner_only_read(method, path):
    if method != "GET":
        return False
    if path in OWNER_DOCUMENTATION_PATHS:
        return True
    if not path.startswith("/api/"):
        return False
    if (
        path.startswith("/api/auth/")
        or path.startswith("/api/bootstrap/")
        or path.startswith("/api/family/")
        or path.startswith("/api/admin/")
    ):
        return False
    return True


def public_health_response():
    return {"status": "ok", "app": config.APP_NAME, "version": config.VERSION}


def family_mission_response():
    try:
        health = get_health()
        overall = "warning" if health.get("warnings") else "ok"
    except Exception:
        overall = "unknown"
    return {
        "status": "ok",
        "overall_status": overall,
        "safe_mode": None,
        "docker": {"running": 0, "total": 0},
        "active_incidents": [],
    }


def hidden_tasks_response():
    return {
        "status": "hidden",
        "lists": [],
        "total": 0,
        "unavailable_lists": 0,
        "stale": False,
        "can_add": False,
        "can_complete": False,
        "can_edit": False,
        "can_remove": False,
    }


def hidden_safety_response():
    hidden = status_item("unknown", "Skjult")
    return {
        "status": "hidden",
        "internet": hidden,
        "doors": hidden,
        "motion": hidden,
        "cameras": hidden,
        "temperature": hidden,
        "humidity": hidden,
        "electricity_price": hidden,
    }


@app.on_event("startup")
async def initialize_local_authentication():
    auth_service.initialize()


@app.middleware("http")
async def enforce_local_authentication(request: Request, call_next):
    path = request.url.path
    static_request = path.startswith("/static/")
    session_value = None if static_request else request.cookies.get(SESSION_COOKIE_NAME)
    current_user = auth_service.resolve_session(session_value) if session_value else None
    request.state.current_user = current_user
    actor_context = set_current_actor(current_user["username"] if current_user else None)
    owner_page = path in {"/admin", "/setup"}
    owner_api = path.startswith("/api/admin/")
    owner_read = is_owner_only_read(request.method, path)
    routine_progress_write = (
        request.method == "POST"
        and path.startswith("/api/family/routines/")
        and "/definitions/" not in path
        and path.rsplit("/", 1)[-1] in ROUTINE_WRITE_ACTIONS
    )
    routine_definition_write = (
        path.startswith("/api/family/routines/definitions/")
        and (
            request.method == "PUT"
            or (request.method == "POST" and path.endswith("/reset-default"))
        )
    )
    routine_write = routine_progress_write or routine_definition_write
    family_task_write = (
        request.method in {"POST", "PUT", "DELETE"}
        and path.startswith("/api/family/tasks/")
    )
    protected_write = (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and path.startswith("/api/")
        and not path.startswith("/api/auth/")
        and not path.startswith("/api/bootstrap/")
        and not routine_write
        and not family_task_write
    )
    try:
        if request.method == "GET" and path in {"/login", "/bootstrap", "/setup", "/admin"}:
            installation = setup_status(db_path=config.DB_PATH)
            if installation["state"] == BOOTSTRAP_REQUIRED and path == "/login":
                return RedirectResponse("/bootstrap", status_code=303)
            if current_user and current_user.get("role") == "owner":
                if path == "/admin" and installation["state"] != READY:
                    return RedirectResponse("/setup", status_code=303)
                if path == "/setup" and installation["state"] == READY:
                    return RedirectResponse("/admin", status_code=303)

        if request.method == "GET" and path == "/":
            return HTMLResponse(render_family_page(current_user))

        if request.method == "GET" and path == "/api/health" and (not current_user or current_user.get("role") != "owner"):
            return JSONResponse(public_health_response())

        if request.method == "GET" and path == "/api/mission" and (not current_user or current_user.get("role") != "owner"):
            return JSONResponse(family_mission_response())

        if request.method == "GET" and path == "/api/family/tasks" and family_feature_hidden(current_user, "tasks"):
            return JSONResponse(hidden_tasks_response())

        if request.method == "GET" and path == "/api/family/safety-status":
            if not current_user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            if current_user.get("role") not in WALL_ROLES:
                return JSONResponse({"detail": "Family role required"}, status_code=403)
            if family_feature_hidden(current_user, "safety"):
                return JSONResponse(hidden_safety_response())

        if request.method == "GET" and (path == "/wall" or path.startswith("/wall/")):
            if not current_user:
                return RedirectResponse(wall_login_target(path), status_code=303)
            if current_user.get("role") not in WALL_ROLES:
                return JSONResponse({"detail": "Family role required"}, status_code=403)
            screen_slug = "wall" if path == "/wall" else path.split("/", 2)[2]
            try:
                return HTMLResponse(render_wall_page(current_user, screen_slug))
            except PermissionError:
                return JSONResponse(
                    {"detail": "This wall account is not assigned to this screen"},
                    status_code=403,
                )
            except LookupError:
                return JSONResponse({"detail": "Screen not found"}, status_code=404)
            except ValueError:
                return JSONResponse({"detail": "Invalid screen"}, status_code=404)

        if owner_page:
            if not current_user:
                return RedirectResponse(f"/login?next={path}", status_code=303)
            if current_user["role"] != "owner":
                return JSONResponse({"detail": "Owner role required"}, status_code=403)

        if owner_api or owner_read:
            if not current_user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            if current_user["role"] != "owner":
                return JSONResponse({"detail": "Owner role required"}, status_code=403)

        if routine_write:
            if not current_user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            allowed_roles = EDITOR_ROLES if routine_definition_write else ROUTINE_ROLES
            if current_user.get("role") not in allowed_roles:
                return JSONResponse({"detail": "Adult role required" if routine_definition_write else "Family role required"}, status_code=403)
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = current_user.get("csrf_value", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                return JSONResponse({"detail": "Invalid request token"}, status_code=403)

        if family_task_write:
            if not current_user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            if family_feature_hidden(current_user, "tasks"):
                return JSONResponse({"detail": "Task access is hidden"}, status_code=403)
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = current_user.get("csrf_value", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                return JSONResponse({"detail": "Invalid request token"}, status_code=403)

        if protected_write:
            if not current_user:
                return JSONResponse({"detail": "Authentication required"}, status_code=401)
            if current_user["role"] != "owner":
                return JSONResponse({"detail": "Owner role required"}, status_code=403)
            supplied = request.headers.get("X-CSRF-Token", "")
            expected = current_user.get("csrf_value", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                return JSONResponse({"detail": "Invalid request token"}, status_code=403)

        response = await call_next(request)
        if static_request:
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        if (protected_write or family_task_write) and current_user:
            log_action(
                "authenticated_write",
                path,
                "ok" if response.status_code < 400 else "error",
                f"actor={current_user['username']}, status={response.status_code}",
            )
        return response
    finally:
        reset_current_actor(actor_context)
