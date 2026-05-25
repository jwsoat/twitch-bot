from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any
import aiohttp

logger = logging.getLogger(__name__)


class HAClient:
    def __init__(self, base_url: str, token: str, session: aiohttp.ClientSession):
        self._base = base_url
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        self._session = session

    async def get_states(self) -> list[dict]:
        async with self._session.get(
            f"{self._base}/api/states", headers=self._headers
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def call_service(
        self, domain: str, service: str, data: dict[str, Any]
    ) -> None:
        url = f"{self._base}/api/services/{domain}/{service}"
        async with self._session.post(
            url, headers=self._headers, json=data
        ) as resp:
            resp.raise_for_status()
