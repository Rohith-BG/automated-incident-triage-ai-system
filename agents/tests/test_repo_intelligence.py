"""Unit tests for the repo_intelligence MCP server parsers and mock provider."""

import pytest

from agents.config import AgentSettings
from agents.mcp_servers.repo_intelligence.mock import (
    MockRepoIntelligenceProvider,
)
from agents.mcp_servers.repo_intelligence.parsers import (
    parse_docker_compose,
    parse_go_mod,
    parse_imports,
    parse_package_json,
    parse_requirements_txt,
)


class TestParsers:
    def test_parse_package_json(self) -> None:
        records = parse_package_json(
            '{"dependencies": {"express": "^4.0.0", "pg": "8.0.0"}}',
            "package.json",
        )
        assert len(records) == 2
        assert records[0]["name"] == "express"
        assert records[0]["evidence"].startswith("package.json:")

    def test_parse_requirements_txt(self) -> None:
        records = parse_requirements_txt(
            "requests>=2.0\nflask==2.1\n# comment\n",
            "requirements.txt",
        )
        assert {r["name"] for r in records} == {"requests", "flask"}

    def test_parse_go_mod(self) -> None:
        records = parse_go_mod(
            "module example\nrequire github.com/gin-gonic/gin v1.8.0\n",
            "go.mod",
        )
        assert records[0]["name"] == "github.com/gin-gonic/gin"
        assert records[0]["version"] == "v1.8.0"

    def test_parse_docker_compose(self) -> None:
        content = (
            "version: '3'\n"
            "services:\n"
            "  frontend:\n"
            "    image: fe\n"
            "    depends_on:\n"
            "      - cart-service\n"
        )
        records = parse_docker_compose(content, "docker-compose.yml")
        kinds = {r["kind"] for r in records}
        assert "deployable" in kinds
        assert "internal_service" in kinds
        assert any(r["name"] == "cart-service" for r in records)

    def test_parse_imports_python(self) -> None:
        imports = parse_imports(
            "import os\nfrom datetime import datetime\n", "main.py", "python"
        )
        modules = {i["module"] for i in imports}
        assert {"os", "datetime"} == modules

    def test_parse_imports_ts(self) -> None:
        imports = parse_imports(
            "import { x } from 'lodash';\n", "index.ts", "typescript"
        )
        assert imports[0]["module"] == "lodash"


class TestMockProvider:
    @pytest.mark.asyncio
    async def test_list_repositories(self) -> None:
        provider = MockRepoIntelligenceProvider(AgentSettings().DATA_DIR)
        repos = await provider.list_repositories("acme")
        assert any(r["name"] == "frontend" for r in repos)

    @pytest.mark.asyncio
    async def test_infer_dependencies_from_fixture(self) -> None:
        provider = MockRepoIntelligenceProvider(AgentSettings().DATA_DIR)
        result = await provider.infer_dependencies(
            repo="acme/frontend",
            service_id="frontend",
            architecture_type="microservice",
        )
        to_ids = {d["to"] for d in result["dependencies"]}
        assert "cart-service" in to_ids
        assert all("evidence" in d for d in result["dependencies"])

    @pytest.mark.asyncio
    async def test_architecture_inspection(self) -> None:
        provider = MockRepoIntelligenceProvider(AgentSettings().DATA_DIR)
        result = await provider.inspect_architecture(
            repo="acme/cart-service", architecture_type="microservice"
        )
        assert result["service_id"] == "cart-service"
        assert result["architecture_type"] == "microservice"