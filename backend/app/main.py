from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from .core.config import settings
from .core.database import init_db, AsyncSessionLocal
from .core.logging import configure_logging
from .exceptions import ExceptionHandlerRegistry
from .routes.alerts import router as alerts_router
from .routes.auth import router as auth_router
from .routes.config import router as config_router
from .routes.dashboard import router as dashboard_router
from .routes.incidents import router as incidents_router
from .routes.services import router as services_router
from .routes.incident_knowledge import router as incident_knowledge_router
from .routes.kg_bootstrap import router as kg_bootstrap_router
from .routes.kg_proposals import router as kg_proposals_router
from .routes.notifications import router as notifications_router
from .routes.onboarding import router as onboarding_router
from .routes.service_registry import router as service_registry_router
from .routes.traces import router as traces_router
from .websocket import router as websocket_router

configure_logging(settings)

import logging

logger = logging.getLogger(__name__)


async def _seed_admin_if_needed() -> None:
    """Seed the initial admin user from env vars if no users exist.

    Reads ADMIN_EMAIL and ADMIN_PASSWORD from Settings. If the user
    table is empty and both vars are set, creates an admin account.
    Skips silently when env vars are absent (dev without seeding).
    """
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return

    from .core.security import hash_password
    from .enums import UserRole
    from .repositories.user import UserRepository

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session=session)
        if await repo.count() > 0:
            return

        user = await repo.create(
            email=settings.ADMIN_EMAIL,
            hashed_password=hash_password(settings.ADMIN_PASSWORD),
            full_name="Platform Admin",
            role=UserRole.ADMIN,
        )
        await session.commit()
        logger.info(
            "Seeded initial admin user: %s (%s)",
            user.id,
            settings.ADMIN_EMAIL,
        )


async def _recover_stale_investigations() -> None:
    """Mark any INVESTIGATING incidents as FAILED on startup.

    When the process restarts (e.g. Uvicorn --reload), background
    orchestrator tasks are killed mid-flight, leaving incidents
    permanently stuck. This recovers them to a terminal status
    so they can be re-triggered via POST /{id}/investigate.
    """
    from sqlalchemy import select, update
    from .models.incident import Incident
    from .enums import IncidentStatus

    async with AsyncSessionLocal() as session:
        # Find stale IDs first (SQLite-compatible)
        result = await session.execute(
            select(Incident.id).where(
                Incident.status == IncidentStatus.INVESTIGATING.value
            )
        )
        stale_ids = [row[0] for row in result.fetchall()]

        if stale_ids:
            await session.execute(
                update(Incident)
                .where(
                    Incident.status
                    == IncidentStatus.INVESTIGATING.value
                )
                .values(status=IncidentStatus.FAILED.value)
            )
            await session.commit()
            logger.warning(
                "Recovered %d stale investigating incident(s): %s",
                len(stale_ids),
                stale_ids,
            )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Initialize database connections and schema
    await init_db()

    # Seed initial admin from env vars (first startup only)
    await _seed_admin_if_needed()

    # Mark any stale investigating incidents as failed
    await _recover_stale_investigations()

    # Import and start background workers
    from backend.app.workers.alert_worker import AlertWorker
    from backend.app.workers.deploy_worker import DeployWorker
    from agents.config import AgentSettings
    from backend.app.services.service_registry import KGProposalService
    from agents.mcp_client.factory import create_mcp_client
    from backend.app.repositories.kg_change_proposal import KGChangeProposalRepository
    from backend.app.repositories.service_registry import ServiceRegistryRepository
    from agents.knowledge_graph.factory import create_kg_store as create_knowledge_graph

    # Create worker instances with proper dependencies
    agent_settings = AgentSettings()
    alert_worker = AlertWorker(
        session_factory=AsyncSessionLocal,
        aws_region=agent_settings.AWS_REGION,
        queue_url=agent_settings.ALERT_SQS_QUEUE_URL,
        dlq_url=agent_settings.ALERT_SQS_DLQ_URL,
    )

    # Create dependencies for DeployWorker
    # These sessions are long-lived worker dependencies, so they are held for
    # the process lifetime and released on shutdown. Creating them per-request
    # is not possible because KGProposalService is bound once at startup.
    startup_sessions = [AsyncSessionLocal(), AsyncSessionLocal()]
    proposal_repo = KGChangeProposalRepository(startup_sessions[0])
    service_repo = ServiceRegistryRepository(startup_sessions[1])
    deploy_mcp_client = create_mcp_client(agent_settings)
    await deploy_mcp_client.initialize()
    proposal_service = KGProposalService(
        proposal_repo=proposal_repo,
        kg_store=create_knowledge_graph(agent_settings),
        deploy_mcp_client=deploy_mcp_client,
        service_registry_repo=service_repo,
    )

    # Auto-sync services from active KG on startup if registry is empty
    try:
        existing_services = await service_repo.list_all(active_only=False)
        if not existing_services:
            synced_count = await proposal_service.sync_services_from_kg()
            await startup_sessions[1].commit()
            logger.info("Startup auto-synced %d services from KG to registry", synced_count)
    except Exception as exc:
        logger.warning("Could not auto-sync KG services to registry on startup: %s", exc)

    deploy_worker = DeployWorker(
        proposal_service=proposal_service,
        deploy_mcp_client=deploy_mcp_client,
        config=agent_settings,
        aws_region=agent_settings.AWS_REGION,
        queue_url=agent_settings.DEPLOY_SQS_QUEUE_URL,
        dlq_url=agent_settings.DEPLOY_SQS_DLQ_URL,
    )

    # Start workers as background tasks
    alert_task = asyncio.create_task(alert_worker.start())
    deploy_task = asyncio.create_task(deploy_worker.start())

    yield

    # Shutdown workers gracefully
    alert_worker._running = False
    deploy_worker._running = False
    await alert_task
    await deploy_task
    await deploy_mcp_client.shutdown()

    # Release the worker-held sessions so their pooled connections are
    # returned instead of being pinned for the process lifetime.
    for session in startup_sessions:
        await session.close()


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
app.include_router(dashboard_router)
app.include_router(traces_router)
app.include_router(config_router)
app.include_router(incident_knowledge_router)
app.include_router(service_registry_router)
app.include_router(onboarding_router)
app.include_router(kg_proposals_router)
app.include_router(kg_bootstrap_router)
app.include_router(notifications_router)
app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(websocket_router)



@app.get("/health")
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "environment": settings.ENVIRONMENT,
    }
