from fastapi import APIRouter, Depends

from app.auth.dependencies import require_owner
from app.integration_status import integration_status


router = APIRouter(prefix="/api/admin/integrations", tags=["admin integrations"])


@router.get("/status")
def get_integration_status(_owner=Depends(require_owner)):
    return integration_status()
