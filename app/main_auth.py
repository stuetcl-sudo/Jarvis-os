import hmac

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.auth.context import reset_current_actor, set_current_actor
from app.auth.routes import router as auth_router
from app.auth.service import SESSION_COOKIE_NAME, auth_service
from app.db import log_action
from app.family_view import render_family_page
from app.main import app
from app.weather import router as weather_router

app.include_router(auth_router)
app.include_router(weather_router)


@app.on_event("startup")
async def initialize_local_authentication():
    auth_service.initialize()


@app.middleware("http")
async def enforce_local_authentication(request: Request, call_next):
    session_value = request.cookies.get(SESSION_COOKIE_NAME)
    current_user = auth_service.resolve_session(session_value) if session_value else None
    request.state.current_user = current_user
    actor_context = set_current_actor(current_user["username"] if current_user else None)
    protected_write = (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.url.path.startswith("/api/")
        and not request.url.path.startswith("/api/auth/")
    )
    try:
        if request.method == "GET" and request.url.path == "/":
            return HTMLResponse(render_family_page(current_user))

        if request.url.path == "/admin":
            if not current_user:
                return RedirectResponse("/login?next=/admin", status_code=303)
            if current_user["role"] != "owner":
                return JSONResponse({"detail": "Owner role required"}, status_code=403)

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
                request.url.path,
                "ok" if response.status_code < 400 else "error",
                f"actor={current_user['username']}, status={response.status_code}",
            )
        return response
    finally:
        reset_current_actor(actor_context)
