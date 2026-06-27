import asyncio
import json
from pathlib import Path
from typing import Any

from ..core.config import settings


class ServiceCatalogRepository:

    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog_path = catalog_path or settings.DATA_DIR / "services.json"

    async def load_catalog(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._load_catalog_sync)

    def _load_catalog_sync(self) -> dict[str, Any]:
        with self.catalog_path.open(encoding="utf-8") as catalog_file:
            catalog = json.load(catalog_file)

        if not isinstance(catalog.get("services"), list):
            raise ValueError("Service catalog must include a services list.")

        return catalog
