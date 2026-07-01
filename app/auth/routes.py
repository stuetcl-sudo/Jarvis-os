from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app import config
from app.auth.dependencies import require_authenticated_user, require_csrf
from app.auth.service import (
    GENERIC_LOGIN_ERROR,
    GENERIC_RATE_LIMIT_ERROR,
    SESSION_COOKIE_NAME,
    InvalidCredentials,
    LoginRateLimited,
    auth_service,
)

router = APIRouter()
LOGIN_TEMPLATE = Path("app/static/login.html")


class LoginPayload(BaseModel):
    username: str
    password: str

    @property
    def credential_value(self) -> str:
        return self.password


def public_user(user, include_csrf=False):
    result = {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }
    if include_csrf:
        result["csrf_token"] = user["csrf_value"]
    return result


@router.get("/login", response_class=HTMLResponse)
def login_page():
    html = LOGIN_TEMPLATE.read_text(encoding="utf-8")
    notice = ""
    if not auth_service.owner_exists():
        notice = (
            '<aside class="owner-setup" role="status"><strong>Ingen aktiv ejer findes endnu.</strong>'
            '<span>Opret den første ejer lokalt fra serverens terminal:</span>'
            '<code>docker compose exec jarvis-os python -m app.auth.cli create-user --username owner --display-name "Owner" --role owner</code></aside>'
        )
    return HTMLResponse(html.replace("<!--OWNER_SETUP_NOTICE-->", notice))


@router.post("/api/auth/login")
def login(payload: LoginPayload, request: Request):
    client_address = request.client.host if request.client else "unknown"
    try:
        session = auth_service.authenticate(payload.username, payload.credential_value, client_address)
    except LoginRateLimited:
        raise HTTPException(status_code=429, detail=GENERIC_RATE_LIMIT_ERROR)
    except InvalidCredentials:
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)
    response = JSONResponse({"user": public_user(session["user"])})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session["session_value"],
        max_age=session["cookie_max_age"],
        expires=session["cookie_max_age"],
        path="/",
        secure=config.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return response


@router.get("/api/auth/me")
def me(user=Depends(require_authenticated_user)):
    return public_user(user, include_csrf=True)


@router.post("/api/auth/logout")
def logout(request: Request, user=Depends(require_csrf)):
    session_value = request.cookies.get(SESSION_COOKIE_NAME)
    auth_service.logout(session_value, user["username"])
    response = JSONResponse({"status": "ok"})
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=config.AUTH_COOKIE_SECURE,
        httponly=True,
        samesite="strict",
    )
    return response
