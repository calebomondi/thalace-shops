import contextlib

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import mcp_server, worker
from app.api.v1.routes import api_router
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    InvalidInputError,
    NotFoundError,
    RateLimitedError,
    ServiceError,
    UnavailableError,
)
from config import settings

_STATUS: dict[type[ServiceError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    ForbiddenError: 403,
    InvalidInputError: 422,
    RateLimitedError: 429,
    UnavailableError: 503,
}


def add_service_error_handlers(app: FastAPI) -> None:
    """Services raise domain errors; this turns them into HTTP answers with
    the service's own (user-safe) message."""

    async def handle(_: Request, exc: ServiceError) -> JSONResponse:
        code = next((c for kind, c in _STATUS.items() if isinstance(exc, kind)), 400)
        headers = {}
        if isinstance(exc, RateLimitedError) and exc.retry_after_s:
            headers["Retry-After"] = str(exc.retry_after_s)
        return JSONResponse({"detail": str(exc)}, status_code=code, headers=headers)

    app.add_exception_handler(ServiceError, handle)


def create_app() -> FastAPI:
    mcp_routes, mcp_sessions = mcp_server.build_app()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        # The MCP routes are added to this app rather than mounted with their
        # own lifespan, so their session manager is started here, alongside
        # the payment watcher.
        async with mcp_sessions.run(), worker.running():
            yield

    app = FastAPI(title=settings.project_name, lifespan=lifespan)
    if settings.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True,
                           allow_methods=["*"], allow_headers=["*"])
    app.include_router(api_router, prefix=settings.api_v1_str)
    add_service_error_handlers(app)
    # The MCP endpoint, as a route of this app so /mcp needs no redirect.
    app.router.routes.extend(mcp_routes)
    return app


app = create_app()
