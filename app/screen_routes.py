from fastapi import APIRouter
from pydantic import BaseModel
from starlette.responses import JSONResponse

from app.screen_registry import delete_screen, list_screens, upsert_screen

router = APIRouter()


class ScreenPayload(BaseModel):
    name: str
    slug: str
    screen_type: str = "wall-large"
    modules: list[str] | None = None
    is_active: bool = True


@router.get("/api/admin/screens")
def api_list_screens():
    return {"status": "ok", "screens": list_screens()}


@router.post("/api/admin/screens")
def api_create_or_update_screen(payload: ScreenPayload):
    try:
        screen = upsert_screen(
            payload.name,
            payload.slug,
            payload.screen_type,
            payload.modules,
            payload.is_active,
        )
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return {"status": "ok", "screen": screen}


@router.delete("/api/admin/screens/{slug}")
def api_delete_screen(slug: str):
    try:
        delete_screen(slug)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    return {"status": "ok"}
