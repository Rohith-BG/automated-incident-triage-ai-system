from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import Base, engine, init_db
from .core.logging import configure_logging
from .exceptions import ExceptionHandlerRegistry
from .routes.alerts import router as alerts_router
from .routes.services import router as services_router

configure_logging(settings)

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ExceptionHandlerRegistry().register(app)

app.include_router(services_router)
app.include_router(alerts_router)


@app.on_event("startup")
async def startup_event() -> None:
    # Initialize database connections and schema
    await init_db()


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
    }
