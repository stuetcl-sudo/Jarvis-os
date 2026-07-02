import hmac

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth.context import reset_current_actor, set_current_actor
from app.auth.routes import router as auth_router
from app.auth.service import SESSION_COOKIE_NAME, auth_service
from app.calendar import router as calendar_router
from app.db import log_action
from app.family_tasks import router as family_tasks_router
from app.family_view import render_family_page
from app.main import app
from app.meal_plan import router as meal_plan_router
from app.routine_definitions import EDITOR_ROLES
from app.routines import ROUTINE_ROLES, router as routines_router
from app.wall_view import WALL_ROLES, render_wall_page
from app.weather import router as weather_router

app.include_router(auth_router)
app.include_router(weather_router)
app.include_router(calendar_router)
app.include_router(meal_plan_router)
app.include_router(family_tasks_router)
app.include_router(routines_router)

ROUTINE_WRITE_ACTIONS = {"complete", "back", "reset"}


@app.on_event("startup")
async def initialize_local_authentication():
    auth_service.initialize()


@app.middleware("http")
async def enforce_local_authentication(request: Request, call_next):
    session_value = request.cookies.get(SESSION_COOKIE_NAME)
    current_user = auth_service.resolve_session(session_value) if session_value else None
    request.state.current_user = current_user
    actor_context = set_current_actor(current_user["username"] if current_user else None)
    path = request.url.path
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
    protected_write = (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and path.startswith("/api/")
        and not path.startswith("/api/auth/")
        and not routine_write
    )
    try:
        if request.method == "GET" and path == "/":
            return HTMLResponse(render_family_page(current_user))

        if request.method == "GET" and path == "/wall":
            if not current_user:
                return RedirectResponse("/login?next=/wall", status_code=303)
            if current_user.get("role") not in WALL_ROLES:
                return JSONResponse({"detail": "Family role required"}, status_code=403)
            return HTMLResponse(render_wall_page(current_user))

        if path == "/admin":
            if not current_user:
                return RedirectResponse("/login?next=/admin", status_code=303)
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
        if protected_write and current_user:
            log_action(
                "authenticated_write",
                path,
                "ok" if response.status_code < 400 else "error",
                f"actor={current_user['username']}, status={response.status_code}",
            )
        return response
    finally:
        reset_current_actor(actor_context)
