"""
Application configuration management.
Reads from global .env file at project root.
"""
from pathlib import Path
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


# Get project root (3 levels up from this file)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    ENVIRONMENT: Literal["dev", "prod"] = "dev"

    # API
    API_TITLE: str = "Automated Incident Triage AI System"
    API_VERSION: str = "1.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Logging
    LOG_LEVEL: str = "INFO"

    # PostgreSQL Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/incident_triage"

    # Neo4j Knowledge Graph
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # LLM provider configuration
    LLM_PROVIDER: Optional[str] = None
    LLM_MODEL: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 60

    # AWS (Production only)
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "ap-south-1"

    # GitHub
    GITHUB_TOKEN: Optional[str] = None
    GITHUB_ORG: Optional[str] = None
    GITHUB_REPO: Optional[str] = None
    GITHUB_WEBHOOK_SECRET: Optional[str] = None

    # Prometheus (Production only)
    PROMETHEUS_URL: str = "http://prometheus:9090"

    # MCP Server Ports
    LOGS_AGENT_PORT: int = 8001
    DEPLOY_AGENT_PORT: int = 8002
    METRICS_AGENT_PORT: int = 8003
    RUNBOOK_AGENT_PORT: int = 8004
    CODE_DIFF_AGENT_PORT: int = 8005

    # Slack
    SLACK_WEBHOOK_URL: Optional[str] = None

    # Services
    SERVICES: str = "frontend,cart-service,product-catalog-service,currency-service,payment-service,shipping-service,email-service,checkout-service,recommendation-service,ad-service"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Data paths (for dev mode)
    DATA_DIR: Path = PROJECT_ROOT / "data"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def is_dev_mode(self) -> bool:
        """Check if running in local development mode."""
        return self.ENVIRONMENT == "dev"

    @property
    def is_prod_mode(self) -> bool:
        """Check if running in production mode."""
        return self.ENVIRONMENT == "prod"

    @property
    def services_list(self) -> list[str]:
        """Get list of services from comma-separated string."""
        return [s.strip() for s in self.SERVICES.split(",")]


# Global settings instance
settings = Settings()
