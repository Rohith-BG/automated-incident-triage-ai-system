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



@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Initialize database connections and schema
    await init_db()

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
    proposal_repo = KGChangeProposalRepository(AsyncSessionLocal())
    service_repo = ServiceRegistryRepository(AsyncSessionLocal())
    deploy_mcp_client = create_mcp_client(agent_settings)
    await deploy_mcp_client.initialize()
    proposal_service = KGProposalService(
        proposal_repo=proposal_repo,
        kg_store=create_knowledge_graph(agent_settings),
        deploy_mcp_client=deploy_mcp_client,
    )
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
