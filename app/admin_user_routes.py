from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.auth.service import auth_service


router = APIRouter()
CREATABLE_ROLES = {"adult", "child", "wall_display"}


class CreateUserPayload(BaseModel):
    username: str
    display_name: str
    role: str
    password: str


def _public_user(user):
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "disabled": user["disabled"],
    }


@router.get("/api/admin/users")
def api_list_users():
    return {"status": "ok", "users": [_public_user(user) for user in auth_service.list_users()]}


@router.post("/api/admin/users", status_code=201)
def api_create_user(payload: CreateUserPayload):
    if payload.role not in CREATABLE_ROLES:
        return JSONResponse({"detail": "Ugyldig rolle."}, status_code=400)
    if not payload.display_name.strip():
        return JSONResponse({"detail": "Navn skal udfyldes."}, status_code=400)
    try:
        user = auth_service.create_user(
            payload.username,
            payload.display_name,
            payload.role,
            payload.password,
        )
    except ValueError as exc:
        messages = {
            "Username is required": "Brugernavn skal udfyldes.",
            "Username already exists": "Brugernavnet findes allerede.",
            "Invalid role": "Ugyldig rolle.",
            "Password must be text": "Adgangskoden er ugyldig.",
            "Password must be at least 12 characters": "Adgangskoden skal være mindst 12 tegn.",
            "Password must be at most 128 characters": "Adgangskoden må højst være 128 tegn.",
        }
        return JSONResponse({"detail": messages.get(str(exc), "Brugeren kunne ikke oprettes.")}, status_code=400)
    return {"status": "created", "message": "Brugeren er oprettet.", "user": _public_user(user)}
