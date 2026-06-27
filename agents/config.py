"""
Agent-layer configuration.

Owns all settings for the investigation pipeline:
MCP servers, LLM, knowledge graph, orchestrator,
evaluation, and swappable-component selectors.

Reads from the same root `.env` file as the backend.
Backend imports `backend.app.core.config.Settings`.
Agents import `agents.config.AgentSettings`.
No cross-imports between the two.
"""

from pathlib import Path
from typing import Literal, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root — one level up from agents/
PROJECT_ROOT = Path(__file__).parent.parent


class AgentSettings(BaseSettings):
    """Settings for the agent investigation layer."""

    # ── Environment ──────────────────────────────────────
    ENVIRONMENT: Literal["dev", "prod"] = "dev"

    # ── Swappable-component selectors (§4 of AGENTS.md) ─
    KG_BACKEND: Literal["in_memory", "neo4j"] = "in_memory"
    LOG_BACKEND: Literal["mock", "loki"] = "mock"
    METRICS_BACKEND: Literal["mock", "prometheus"] = "mock"
    LLM_PROVIDER: Literal[
        "google", "openai", "anthropic", "local"
    ] = "google"
    NOTIFICATION_BACKEND: Literal[
        "console", "slack"
    ] = "console"
    TICKET_BACKEND: Literal["noop", "jira"] = "noop"

    # ── LLM ──────────────────────────────────────────────
    GOOGLE_API_KEY: Optional[str] = None
    LLM_API_KEY: Optional[str] = None
    LLM_MODEL: str = "gemini-2.0-flash"
    LLM_BASE_URL: Optional[str] = None
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_MAX_RETRIES: int = 2
    LLM_TEMPERATURE: float = 0.2

    # ── Knowledge Graph ──────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    SERVICES_JSON_PATH: Path = PROJECT_ROOT / "data" / "services.json"

    # ── MCP Server addresses ─────────────────────────────
    MCP_LOGS_URL: str = "http://localhost:8001"
    MCP_METRICS_URL: str = "http://localhost:8003"
    MCP_CODE_DIFF_URL: str = "http://localhost:8005"

    # ── Orchestrator ─────────────────────────────────────
    CONFIDENCE_THRESHOLD: float = 0.6
    TOOL_TIMEOUT_SECONDS: int = 30
    TOOL_MAX_RETRIES: int = 2
    DEDUP_WINDOW_SECONDS: int = 300  # 5 min

    # ── Evaluation & Tracing ─────────────────────────────
    TRACING_ENABLED: bool = True
    EVAL_GOLDEN_DATASET_PATH: Optional[Path] = None

    # ── Data directory (dev-mode fixtures) ───────────────
    DATA_DIR: Path = PROJECT_ROOT / "data"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Validators ───────────────────────────────────────

    @field_validator("CONFIDENCE_THRESHOLD")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        """Confidence must be between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(
                f"CONFIDENCE_THRESHOLD must be 0..1, got {v}"
            )
        return v

    @field_validator("LLM_TEMPERATURE")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Temperature must be between 0 and 2."""
        if not 0.0 <= v <= 2.0:
            raise ValueError(
                f"LLM_TEMPERATURE must be 0..2, got {v}"
            )
        return v

    # ── Convenience properties ───────────────────────────

    @property
    def is_dev(self) -> bool:
        """True when running in local development mode."""
        return self.ENVIRONMENT == "dev"

    @property
    def is_prod(self) -> bool:
        """True when running in production."""
        return self.ENVIRONMENT == "prod"

    @property
    def uses_neo4j(self) -> bool:
        """True when knowledge graph is backed by Neo4j."""
        return self.KG_BACKEND == "neo4j"

    @property
    def uses_mock_logs(self) -> bool:
        """True when log source is mock data."""
        return self.LOG_BACKEND == "mock"

    @property
    def uses_mock_metrics(self) -> bool:
        """True when metrics source is mock data."""
        return self.METRICS_BACKEND == "mock"


# Singleton — import this everywhere in agents/
agent_settings = AgentSettings()
