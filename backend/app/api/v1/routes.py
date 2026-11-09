from fastapi import APIRouter

from app.api.v1.endpoints import me, shops
from app.api.v1.endpoints.admin import platform as admin_platform
from config import settings

api_router = APIRouter()


@api_router.get("/health")
async def health() -> dict:
    return {"status": "ok", "project": settings.project_name, "environment": settings.environment}


api_router.include_router(me.router)
api_router.include_router(shops.router)
api_router.include_router(admin_platform.router)
