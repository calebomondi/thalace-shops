from fastapi import APIRouter

from config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "project": settings.project_name, "environment": settings.environment}
