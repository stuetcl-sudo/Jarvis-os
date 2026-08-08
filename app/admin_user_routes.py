from fastapi import APIRouter, Request
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


class PasswordPayload(BaseModel):
    password: str


class UserProfilePayload(BaseModel):
    display_color: str
    family_visible: bool


def _public_user(user):
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
        "disabled": user["disabled"],
        "display_color": user["display_color"],
        "family_visible": user["family_visible"],
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


@router.put("/api/admin/users/{user_id}/profile")
def api_update_user_profile(user_id: str, payload: UserProfilePayload):
    try:
        user = auth_service.update_profile(user_id, payload.display_color, payload.family_visible)
    except ValueError as exc:
        if str(exc) == "User not found":
            return JSONResponse({"detail": "Brugeren findes ikke."}, status_code=404)
        return JSONResponse({"detail": "Farven er ikke tilladt."}, status_code=400)
    return {"status": "ok", "message": "Brugerprofilen er gemt.", "user": _public_user(user)}


@router.post("/api/admin/users/{user_id}/password")
def api_reset_user_password(user_id: str, payload: PasswordPayload, request: Request):
    current_user = getattr(request.state, "current_user", None)
    if current_user and current_user.get("user_id") == user_id:
        return JSONResponse({"detail": "Ejerens egen adgangskode kan ikke ændres her."}, status_code=400)
    try:
        user = auth_service.reset_password_by_id(user_id, payload.password)
    except ValueError as exc:
        messages = {
            "User not found": ("Brugeren findes ikke.", 404),
            "Owner password cannot be changed here": ("Ejerens adgangskode kan ikke ændres her.", 400),
            "Password must be text": ("Adgangskoden er ugyldig.", 400),
            "Password must be at least 12 characters": ("Adgangskoden skal være mindst 12 tegn.", 400),
            "Password must be at most 128 characters": ("Adgangskoden må højst være 128 tegn.", 400),
        }
        message, status = messages.get(str(exc), ("Adgangskoden kunne ikke ændres.", 400))
        return JSONResponse({"detail": message}, status_code=status)
    return {"status": "ok", "message": "Adgangskoden er ændret.", "user": _public_user(user)}


@router.delete("/api/admin/users/{user_id}")
def api_delete_user(user_id: str, request: Request):
    current_user = getattr(request.state, "current_user", None)
    if current_user and current_user.get("user_id") == user_id:
        return JSONResponse({"detail": "Du kan ikke slette din egen ejer."}, status_code=400)
    try:
        auth_service.delete_user(user_id)
    except ValueError as exc:
        if str(exc) == "User not found":
            return JSONResponse({"detail": "Brugeren findes ikke."}, status_code=404)
        return JSONResponse({"detail": "Ejere kan ikke slettes."}, status_code=400)
    return {"status": "deleted", "message": "Brugeren er slettet."}
