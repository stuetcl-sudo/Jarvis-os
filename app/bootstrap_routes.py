from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from app import config
from app.auth.routes import public_user
from app.auth.service import (
    SESSION_COOKIE_NAME,
    BootstrapUnavailable,
    auth_service,
)
from app.setup_state import setup_status


router = APIRouter(tags=["bootstrap"])
BOOTSTRAP_TEMPLATE = Path("app/static/bootstrap.html")


class FirstOwnerPayload(BaseModel):
    display_name: str
    username: str
    password: str


@router.get("/bootstrap", response_class=HTMLResponse)
def bootstrap_page():
    if not auth_service.bootstrap_required():
        return RedirectResponse("/login", status_code=303)

    return HTMLResponse(
        BOOTSTRAP_TEMPLATE.read_text(encoding="utf-8")
    )


@router.get("/api/bootstrap/status")
def bootstrap_status():
    status = setup_status(db_path=config.DB_PATH)
    required = status["state"] == "bootstrap_required"
    return {
        "bootstrap_required": required,
        "owner_exists": not required,
    }


@router.post("/api/bootstrap/owner", status_code=201)
def create_first_owner(payload: FirstOwnerPayload):
    try:
        session = auth_service.create_first_owner(
            payload.username,
            payload.display_name,
            payload.password,
        )
    except BootstrapUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = JSONResponse(
        {
            "status": "created",
            "user": public_user(session["user"]),
            "next": "/setup",
        },
        status_code=201,
    )
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
