from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .core.database import Base, engine, init_db
from .core.logging import configure_logging
from .exceptions import ExceptionHandlerRegistry
from .routes.alerts import router as alerts_router
from .routes.auth import router as auth_router
from .routes.incidents import router as incidents_router
from .routes.services import router as services_router
from .routes.incident_knowledge import router as incident_knowledge_router
from .routes.kg_proposals import router as kg_proposals_router
from .routes.service_registry import router as service_registry_router
from .websocket import router as websocket_router

configure_logging(settings)



@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database connections and schema
    await init_db()
    yield


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan,
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
app.include_router(incidents_router)
app.include_router(incident_knowledge_router)
app.include_router(service_registry_router)
app.include_router(kg_proposals_router)
app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(websocket_router)



@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
    }
