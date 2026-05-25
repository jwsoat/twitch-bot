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


@dataclass(frozen=True)
class Match:
    entity_id: str


@dataclass(frozen=True)
class Ambiguous:
    candidates: list[str]

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Ambiguous):
            return NotImplemented
        return sorted(self.candidates) == sorted(other.candidates)


@dataclass(frozen=True)
class NotFound:
    pass


ResolveResult = Match | Ambiguous | NotFound


class EntityIndex:
    def __init__(self) -> None:
        # domain -> list of (entity_id, friendly_lower, short_lower)
        self._index: dict[str, list[tuple[str, str, str]]] = {}

    def build(self, states: list[dict]) -> None:
        index: dict[str, list[tuple[str, str, str]]] = {}
        for state in states:
            entity_id: str = state.get("entity_id", "")
            if "." not in entity_id:
                continue
            domain, short = entity_id.split(".", 1)
            friendly: str = state.get("attributes", {}).get("friendly_name", short)
            index.setdefault(domain, []).append(
                (entity_id, friendly.lower(), short.lower())
            )
        self._index = index

    def resolve(self, domain: str, query: str) -> ResolveResult:
        entries = self._index.get(domain, [])
        q = query.lower()

        exact = [e[0] for e in entries if e[1] == q or e[2] == q]
        if len(exact) == 1:
            return Match(exact[0])
        if len(exact) > 1:
            return Ambiguous(exact[:5])

        prefix = [e[0] for e in entries if e[1].startswith(q) or e[2].startswith(q)]
        if len(prefix) == 1:
            return Match(prefix[0])
        if len(prefix) > 1:
            return Ambiguous(prefix[:5])

        substr = [e[0] for e in entries if q in e[1] or q in e[2]]
        if len(substr) == 1:
            return Match(substr[0])
        if len(substr) > 1:
            return Ambiguous(substr[:5])

        return NotFound()

    def list_domain(self, domain: str, limit: int = 10) -> list[str]:
        return [e[0] for e in self._index.get(domain, [])[:limit]]
