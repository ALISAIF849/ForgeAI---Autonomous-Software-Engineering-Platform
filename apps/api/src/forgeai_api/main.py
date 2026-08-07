from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forgeai_api.core.config import get_settings
from forgeai_api.core.exceptions import register_exception_handlers
from forgeai_api.middleware.request_context import RequestContextMiddleware
from forgeai_api.modules.auth.router import router as auth_router
from forgeai_api.modules.organizations.router import router as organizations_router
from forgeai_api.modules.workflows.router import router as workflows_router
from forgeai_api.routes.health import router as health_router
from forgeai_core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(log_level=settings.log_level, environment=settings.environment)

    app = FastAPI(
        title="ForgeAI API",
        description="AI-native Software Engineering Workspace — backend API.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(organizations_router, prefix="/api/v1")
    app.include_router(workflows_router, prefix="/api/v1")
    # Projects (a standalone CRUD module, not just the ORM model workflows
    # already references) and the rest of the module set are mounted here as
    # each lands — see the Sprint 2 status report for what exists vs. pending.

    return app


app = create_app()
