from fastapi import APIRouter

from app.api.v1.endpoints import (
    chat,
    group_orders,
    invoices,
    me,
    negotiations,
    offers,
    public,
    rules,
    shops,
    signing,
)
from app.api.v1.endpoints.admin import platform as admin_platform
from config import settings

api_router = APIRouter()


@api_router.get("/health")
async def health() -> dict:
    return {"status": "ok", "project": settings.project_name, "environment": settings.environment}


api_router.include_router(me.router)
api_router.include_router(shops.router)
api_router.include_router(offers.router)
api_router.include_router(rules.router)
api_router.include_router(chat.router)
api_router.include_router(signing.router)
api_router.include_router(invoices.router)
api_router.include_router(negotiations.router)
api_router.include_router(public.router)
api_router.include_router(group_orders.owner)
api_router.include_router(group_orders.public)
api_router.include_router(admin_platform.router)
