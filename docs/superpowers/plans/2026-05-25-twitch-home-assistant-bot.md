# Twitch Home Assistant Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Twitch chat bot that lets four trusted users control Home Assistant (lights, scenes, media, curtains, TTS) via Nabu Casa HTTPS.

**Architecture:** twitchio Bot dispatches commands to async handler functions in commands.py; each handler calls HAClient (aiohttp REST) after resolving entity names via EntityIndex (auto-discovered from /api/states, refreshed every 5 min). Auth is a simple allowlist check before every command.

**Tech Stack:** Python 3.11+, twitchio 2.x, aiohttp 3.x, python-dotenv, pytest, pytest-asyncio, aioresponses

---

## File Map

| File | Responsibility |
|---|---|
| `requirements.txt` | Pinned deps |
| `pytest.ini` | asyncio_mode=auto |
| `.gitignore` | Exclude .env, bot.log, __pycache__ |
| `.env.example` | Template with all vars |
| `config.py` | Load + validate env vars → Config dataclass |
| `auth.py` | `is_allowed(username, allowed_set) -> bool` |
| `homeassistant.py` | `HAClient` (REST), `EntityIndex` (resolve), result types |
| `commands.py` | One async fn per command + `TTSRateLimiter` |
| `bot.py` | twitchio Bot subclass, command wiring, logging setup, `main()` |
| `README.md` | Setup guide + smoke test checklist |
| `tests/conftest.py` | Shared fixtures |
| `tests/test_auth.py` | Allowlist unit tests |
| `tests/test_entity_resolution.py` | EntityIndex unit tests |
| `tests/test_homeassistant.py` | HAClient HTTP mock tests |
| `tests/test_commands.py` | Command handler tests with mocked HA + index |

---

### Task 1: Project scaffold

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Create requirements.txt**

```
twitchio>=2.6,<3
aiohttp>=3.9,<4
python-dotenv>=1.0,<2
pytest>=7.4
pytest-asyncio>=0.23
aioresponses>=0.7.6
```

- [ ] **Step 2: Create pytest.ini**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Create .gitignore**

```
.env
bot.log
bot.log.*
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 4: Create .env.example**

```
# Required
TWITCH_TOKEN=oauth:your_token_here
TWITCH_BOT_NICK=your_bot_username
HA_URL=https://your-id.ui.nabu.casa
HA_TOKEN=your_long_lived_access_token

# Optional (defaults shown)
CHANNELS=directorynetworks,JwsoatMedia,dylanwech,directorynetwork
ALLOWED_USERS=directorynetworks,JwsoatMedia,dylanwech,directorynetwork
TTS_SERVICE=tts.cloud_say
TTS_ENTITY=
TTS_COOLDOWN_SEC=10
ENTITY_REFRESH_SEC=300
COMMAND_PREFIX=!
LOG_LEVEL=INFO
```

- [ ] **Step 5: Install deps**

```
pip install -r requirements.txt
```

Expected: no errors, twitchio/aiohttp/pytest installed.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt pytest.ini .gitignore .env.example
git commit -m "chore: project scaffold"
```

---

### Task 2: config.py

**Files:**
- Create: `config.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_config.py`:

```python
import os
import pytest
from config import load_config


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("TWITCH_TOKEN", raising=False)
    monkeypatch.delenv("TWITCH_BOT_NICK", raising=False)
    monkeypatch.delenv("HA_URL", raising=False)
    monkeypatch.delenv("HA_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        load_config()


def test_loads_required(monkeypatch):
    monkeypatch.setenv("TWITCH_TOKEN", "oauth:abc")
    monkeypatch.setenv("TWITCH_BOT_NICK", "mybot")
    monkeypatch.setenv("HA_URL", "https://example.ui.nabu.casa/")
    monkeypatch.setenv("HA_TOKEN", "token123")
    cfg = load_config()
    assert cfg.twitch_token == "oauth:abc"
    assert cfg.ha_url == "https://example.ui.nabu.casa"  # trailing slash stripped


def test_defaults(monkeypatch):
    monkeypatch.setenv("TWITCH_TOKEN", "oauth:abc")
    monkeypatch.setenv("TWITCH_BOT_NICK", "mybot")
    monkeypatch.setenv("HA_URL", "https://example.ui.nabu.casa")
    monkeypatch.setenv("HA_TOKEN", "token123")
    monkeypatch.delenv("CHANNELS", raising=False)
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    cfg = load_config()
    assert "directorynetworks" in cfg.channels
    assert "jwsoatmedia" in cfg.allowed_users  # stored lowercase
    assert cfg.tts_entity is None
    assert cfg.tts_cooldown_sec == 10
```

- [ ] **Step 2: Run test — verify fail**

```
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Create config.py**

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    twitch_token: str
    twitch_bot_nick: str
    ha_url: str
    ha_token: str
    channels: list[str]
    allowed_users: set[str]
    tts_service: str
    tts_entity: str | None
    tts_cooldown_sec: int
    entity_refresh_sec: int
    command_prefix: str
    log_level: str


def load_config() -> Config:
    def req(key: str) -> str:
        val = os.getenv(key, "").strip()
        if not val:
            raise SystemExit(f"Missing required env var: {key}")
        return val

    return Config(
        twitch_token=req("TWITCH_TOKEN"),
        twitch_bot_nick=req("TWITCH_BOT_NICK"),
        ha_url=req("HA_URL").rstrip("/"),
        ha_token=req("HA_TOKEN"),
        channels=[
            c.strip()
            for c in os.getenv(
                "CHANNELS", "directorynetworks,JwsoatMedia,dylanwech,directorynetwork"
            ).split(",")
            if c.strip()
        ],
        allowed_users={
            u.strip().lower()
            for u in os.getenv(
                "ALLOWED_USERS",
                "directorynetworks,JwsoatMedia,dylanwech,directorynetwork",
            ).split(",")
            if u.strip()
        },
        tts_service=os.getenv("TTS_SERVICE", "tts.cloud_say"),
        tts_entity=os.getenv("TTS_ENTITY", "").strip() or None,
        tts_cooldown_sec=int(os.getenv("TTS_COOLDOWN_SEC", "10")),
        entity_refresh_sec=int(os.getenv("ENTITY_REFRESH_SEC", "300")),
        command_prefix=os.getenv("COMMAND_PREFIX", "!"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
```

- [ ] **Step 4: Run test — verify pass**

```
pytest tests/test_config.py -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: config loading with env validation"
```

---

### Task 3: auth.py

**Files:**
- Create: `auth.py`
- Create: `tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_auth.py`:

```python
from auth import is_allowed


def test_exact_match():
    assert is_allowed("dylanwech", {"dylanwech"})


def test_case_insensitive_input():
    assert is_allowed("DylanWech", {"dylanwech"})


def test_case_insensitive_stored_upper():
    assert is_allowed("directorynetworks", {"DIRECTORYNETWORKS"})


def test_multiple_users():
    allowed = {"directorynetworks", "jwsoatmedia", "dylanwech", "directorynetwork"}
    assert is_allowed("JwsoatMedia", allowed)


def test_blocked_unknown():
    assert not is_allowed("randomviewer", {"dylanwech"})


def test_empty_allowlist_blocks_all():
    assert not is_allowed("dylanwech", set())
```

- [ ] **Step 2: Run — verify fail**

```
pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 3: Create auth.py**

```python
def is_allowed(username: str, allowed: set[str]) -> bool:
    return username.lower() in {u.lower() for u in allowed}
```

- [ ] **Step 4: Run — verify pass**

```
pytest tests/test_auth.py -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add auth.py tests/test_auth.py
git commit -m "feat: allowlist auth check"
```

---

### Task 4: homeassistant.py — HAClient

**Files:**
- Create: `homeassistant.py`
- Create: `tests/test_homeassistant.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_homeassistant.py`:

```python
import pytest
import aiohttp
from aioresponses import aioresponses
from homeassistant import HAClient

BASE = "https://test.ui.nabu.casa"
TOKEN = "testtoken123"


@pytest.fixture
async def client():
    async with aiohttp.ClientSession() as session:
        yield HAClient(BASE, TOKEN, session)


async def test_get_states_returns_list(client):
    states = [{"entity_id": "light.test", "attributes": {"friendly_name": "Test"}}]
    with aioresponses() as m:
        m.get(f"{BASE}/api/states", payload=states)
        result = await client.get_states()
    assert result == states


async def test_get_states_sends_bearer_header(client):
    from yarl import URL
    with aioresponses() as m:
        m.get(f"{BASE}/api/states", payload=[])
        await client.get_states()
        key = ("GET", URL(f"{BASE}/api/states"))
        call = m.requests[key][0]
    assert call.kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"


async def test_call_service_posts_correct_url(client):
    from yarl import URL
    with aioresponses() as m:
        m.post(f"{BASE}/api/services/light/turn_on", payload={})
        await client.call_service("light", "turn_on", {"entity_id": "light.lamp"})
        key = ("POST", URL(f"{BASE}/api/services/light/turn_on"))
    assert key in m.requests


async def test_call_service_sends_json_body(client):
    from yarl import URL
    with aioresponses() as m:
        m.post(f"{BASE}/api/services/light/turn_on", payload={})
        await client.call_service("light", "turn_on", {"entity_id": "light.lamp"})
        key = ("POST", URL(f"{BASE}/api/services/light/turn_on"))
        call = m.requests[key][0]
    assert call.kwargs["json"] == {"entity_id": "light.lamp"}


async def test_call_service_raises_on_401(client):
    with aioresponses() as m:
        m.post(f"{BASE}/api/services/light/turn_on", status=401)
        with pytest.raises(aiohttp.ClientResponseError):
            await client.call_service("light", "turn_on", {})
```

- [ ] **Step 2: Run — verify fail**

```
pytest tests/test_homeassistant.py -v
```

Expected: `ModuleNotFoundError: No module named 'homeassistant'`

- [ ] **Step 3: Create homeassistant.py with HAClient**

```python
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
```

- [ ] **Step 4: Run — verify pass**

```
pytest tests/test_homeassistant.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add homeassistant.py tests/test_homeassistant.py
git commit -m "feat: HAClient REST wrapper"
```

---

### Task 5: homeassistant.py — EntityIndex

**Files:**
- Modify: `homeassistant.py` (append result types + EntityIndex class)
- Create: `tests/test_entity_resolution.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_entity_resolution.py`:

```python
import pytest
from homeassistant import EntityIndex, Match, Ambiguous, NotFound

STATES = [
    {"entity_id": "light.living_room", "attributes": {"friendly_name": "Living Room"}},
    {"entity_id": "light.bedroom", "attributes": {"friendly_name": "Bedroom Light"}},
    {"entity_id": "light.kitchen_lamp", "attributes": {"friendly_name": "Kitchen Lamp"}},
    {"entity_id": "cover.blinds_main", "attributes": {"friendly_name": "Main Blinds"}},
    {"entity_id": "scene.party_mode", "attributes": {"friendly_name": "Party Mode"}},
]


@pytest.fixture
def index():
    idx = EntityIndex()
    idx.build(STATES)
    return idx


def test_exact_friendly_name(index):
    assert index.resolve("light", "Living Room") == Match("light.living_room")


def test_exact_short_id(index):
    assert index.resolve("light", "bedroom") == Match("light.bedroom")


def test_case_insensitive(index):
    assert index.resolve("light", "LIVING ROOM") == Match("light.living_room")


def test_prefix_match(index):
    assert index.resolve("light", "kitchen") == Match("light.kitchen_lamp")


def test_substring_match(index):
    assert index.resolve("light", "room") == Match("light.living_room")


def test_ambiguous_returns_candidates(index):
    result = index.resolve("light", "li")
    assert isinstance(result, Ambiguous)
    assert len(result.candidates) >= 2
    assert all("light." in c for c in result.candidates)


def test_not_found(index):
    assert index.resolve("light", "xyznotexist") == NotFound()


def test_unknown_domain_not_found(index):
    assert index.resolve("switch", "lamp") == NotFound()


def test_other_domain_resolves(index):
    assert index.resolve("cover", "blinds") == Match("cover.blinds_main")


def test_list_domain_returns_entity_ids(index):
    ids = index.list_domain("light")
    assert len(ids) == 3
    assert "light.living_room" in ids


def test_list_domain_respects_limit(index):
    ids = index.list_domain("light", limit=2)
    assert len(ids) == 2


def test_list_domain_empty(index):
    assert index.list_domain("switch") == []


def test_build_ignores_malformed_entity_id():
    idx = EntityIndex()
    idx.build([{"entity_id": "nodomainhere", "attributes": {}}])
    assert idx.list_domain("nodomainhere") == []
```

- [ ] **Step 2: Run — verify fail**

```
pytest tests/test_entity_resolution.py -v
```

Expected: `ImportError: cannot import name 'Match' from 'homeassistant'`

- [ ] **Step 3: Append to homeassistant.py**

Add after the `HAClient` class:

```python
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
```

Also add `from dataclasses import dataclass` import at top of file if not present.

- [ ] **Step 4: Run — verify pass**

```
pytest tests/test_entity_resolution.py -v
```

Expected: 13 PASSED

- [ ] **Step 5: Commit**

```bash
git add homeassistant.py tests/test_entity_resolution.py
git commit -m "feat: EntityIndex with tiered fuzzy resolution"
```

---

### Task 6: commands.py — light commands

**Files:**
- Create: `commands.py`
- Create: `tests/test_commands.py`

- [ ] **Step 1: Write failing tests for light commands**

Create `tests/test_commands.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant import EntityIndex, Match, NotFound, Ambiguous


def make_ctx(channel_name: str = "testchannel") -> MagicMock:
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.name = channel_name
    return ctx


def make_ha() -> AsyncMock:
    ha = AsyncMock()
    ha.call_service = AsyncMock()
    return ha


def make_index(domain: str, entity_id: str, friendly: str) -> EntityIndex:
    idx = EntityIndex()
    idx.build([{"entity_id": entity_id, "attributes": {"friendly_name": friendly}}])
    return idx


# --- light ---

async def test_light_on(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.living_room", "Living Room")
    await cmd_light(ctx, ha, idx, ["Living Room", "on"])
    ha.call_service.assert_called_once_with("light", "turn_on", {"entity_id": "light.living_room"})


async def test_light_off(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_light(ctx, ha, idx, ["lamp", "off"])
    ha.call_service.assert_called_once_with("light", "turn_off", {"entity_id": "light.lamp"})


async def test_light_bad_state(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_light(ctx, ha, idx, ["lamp", "toggle"])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]
    ha.call_service.assert_not_called()


async def test_light_not_found(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = EntityIndex()
    idx.build([])
    await cmd_light(ctx, ha, idx, ["unknown", "on"])
    ctx.send.assert_called_once()
    assert "no light" in ctx.send.call_args[0][0]


async def test_light_ambiguous(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = EntityIndex()
    idx.build([
        {"entity_id": "light.a1", "attributes": {"friendly_name": "Lamp A"}},
        {"entity_id": "light.a2", "attributes": {"friendly_name": "Lamp B"}},
    ])
    await cmd_light(ctx, ha, idx, ["lamp", "on"])
    ctx.send.assert_called_once()
    assert "multiple" in ctx.send.call_args[0][0]


async def test_color(imports):
    from commands import cmd_color
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_color(ctx, ha, idx, ["lamp", "red"])
    ha.call_service.assert_called_once_with(
        "light", "turn_on", {"entity_id": "light.lamp", "color_name": "red"}
    )


async def test_bright_clamps(imports):
    from commands import cmd_bright
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_bright(ctx, ha, idx, ["lamp", "150"])
    ha.call_service.assert_called_once_with(
        "light", "turn_on", {"entity_id": "light.lamp", "brightness_pct": 100}
    )


async def test_bright_invalid_number(imports):
    from commands import cmd_bright
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_bright(ctx, ha, idx, ["lamp", "notanumber"])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]
```

Add a `conftest.py` fixture so imports work from root:

```python
# tests/conftest.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

@pytest.fixture
def imports():
    pass  # ensures sys.path is set before each test
```

- [ ] **Step 2: Run — verify fail**

```
pytest tests/test_commands.py -v -k "light or color or bright"
```

Expected: `ModuleNotFoundError: No module named 'commands'`

- [ ] **Step 3: Create commands.py with light handlers**

```python
from __future__ import annotations
import logging
import time
from typing import Any, Protocol

from homeassistant import HAClient, EntityIndex, Match, Ambiguous, NotFound

logger = logging.getLogger(__name__)


class ChatContext(Protocol):
    async def send(self, message: str) -> None: ...
    channel: Any


async def _resolve(
    ctx: ChatContext, index: EntityIndex, domain: str, name: str
) -> str | None:
    result = index.resolve(domain, name)
    if isinstance(result, Match):
        return result.entity_id
    if isinstance(result, Ambiguous):
        await ctx.send(f"multiple {domain}s: {', '.join(result.candidates)}")
        return None
    await ctx.send(f'no {domain} matching "{name}"')
    return None


async def cmd_light(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2 or args[1].lower() not in ("on", "off"):
        await ctx.send("usage: !light <name> on|off")
        return
    name, state = args[0], args[1].lower()
    entity_id = await _resolve(ctx, index, "light", name)
    if not entity_id:
        return
    service = "turn_on" if state == "on" else "turn_off"
    try:
        await ha.call_service("light", service, {"entity_id": entity_id})
        await ctx.send(f"light {entity_id} {state}")
    except Exception as e:
        logger.error("light error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_color(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2:
        await ctx.send("usage: !color <name> <color>")
        return
    name, color = args[0], args[1].lower()
    entity_id = await _resolve(ctx, index, "light", name)
    if not entity_id:
        return
    try:
        await ha.call_service(
            "light", "turn_on", {"entity_id": entity_id, "color_name": color}
        )
        await ctx.send(f"light {entity_id} color → {color}")
    except Exception as e:
        logger.error("color error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_bright(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2:
        await ctx.send("usage: !bright <name> <0-100>")
        return
    name = args[0]
    try:
        pct = max(0, min(100, int(args[1])))
    except ValueError:
        await ctx.send("usage: !bright <name> <0-100>")
        return
    entity_id = await _resolve(ctx, index, "light", name)
    if not entity_id:
        return
    try:
        await ha.call_service(
            "light", "turn_on", {"entity_id": entity_id, "brightness_pct": pct}
        )
        await ctx.send(f"light {entity_id} brightness → {pct}%")
    except Exception as e:
        logger.error("bright error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 4: Run — verify pass**

```
pytest tests/test_commands.py -v -k "light or color or bright"
```

Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add commands.py tests/test_commands.py tests/conftest.py
git commit -m "feat: light/color/bright command handlers"
```

---

### Task 7: commands.py — scene and media commands

**Files:**
- Modify: `commands.py` (append scene, play, pause, vol handlers)
- Modify: `tests/test_commands.py` (append tests)

- [ ] **Step 1: Append failing tests to tests/test_commands.py**

Add to end of `tests/test_commands.py`:

```python
# --- scene ---

async def test_scene(imports):
    from commands import cmd_scene
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("scene", "scene.party_mode", "Party Mode")
    await cmd_scene(ctx, ha, idx, ["party"])
    ha.call_service.assert_called_once_with(
        "scene", "turn_on", {"entity_id": "scene.party_mode"}
    )


async def test_scene_no_args(imports):
    from commands import cmd_scene
    ctx = make_ctx()
    ha = make_ha()
    idx = EntityIndex()
    idx.build([])
    await cmd_scene(ctx, ha, idx, [])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]


# --- media ---

async def test_play(imports):
    from commands import cmd_play
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_play(ctx, ha, idx, ["tv"])
    ha.call_service.assert_called_once_with(
        "media_player", "media_play", {"entity_id": "media_player.tv"}
    )


async def test_pause(imports):
    from commands import cmd_pause
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_pause(ctx, ha, idx, ["tv"])
    ha.call_service.assert_called_once_with(
        "media_player", "media_pause", {"entity_id": "media_player.tv"}
    )


async def test_vol_sets_fractional(imports):
    from commands import cmd_vol
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_vol(ctx, ha, idx, ["tv", "50"])
    ha.call_service.assert_called_once_with(
        "media_player", "volume_set", {"entity_id": "media_player.tv", "volume_level": 0.5}
    )


async def test_vol_clamps_to_100(imports):
    from commands import cmd_vol
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_vol(ctx, ha, idx, ["tv", "200"])
    ha.call_service.assert_called_once_with(
        "media_player", "volume_set", {"entity_id": "media_player.tv", "volume_level": 1.0}
    )
```

- [ ] **Step 2: Run — verify fail**

```
pytest tests/test_commands.py -v -k "scene or play or pause or vol"
```

Expected: `ImportError: cannot import name 'cmd_scene'`

- [ ] **Step 3: Append to commands.py**

```python
async def cmd_scene(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if not args:
        await ctx.send("usage: !scene <name>")
        return
    entity_id = await _resolve(ctx, index, "scene", args[0])
    if not entity_id:
        return
    try:
        await ha.call_service("scene", "turn_on", {"entity_id": entity_id})
        await ctx.send(f"scene {entity_id} activated")
    except Exception as e:
        logger.error("scene error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_play(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if not args:
        await ctx.send("usage: !play <name>")
        return
    entity_id = await _resolve(ctx, index, "media_player", args[0])
    if not entity_id:
        return
    try:
        await ha.call_service("media_player", "media_play", {"entity_id": entity_id})
        await ctx.send(f"playing {entity_id}")
    except Exception as e:
        logger.error("play error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_pause(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if not args:
        await ctx.send("usage: !pause <name>")
        return
    entity_id = await _resolve(ctx, index, "media_player", args[0])
    if not entity_id:
        return
    try:
        await ha.call_service("media_player", "media_pause", {"entity_id": entity_id})
        await ctx.send(f"paused {entity_id}")
    except Exception as e:
        logger.error("pause error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_vol(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2:
        await ctx.send("usage: !vol <name> <0-100>")
        return
    name = args[0]
    try:
        pct = max(0, min(100, int(args[1])))
    except ValueError:
        await ctx.send("usage: !vol <name> <0-100>")
        return
    entity_id = await _resolve(ctx, index, "media_player", name)
    if not entity_id:
        return
    try:
        await ha.call_service(
            "media_player",
            "volume_set",
            {"entity_id": entity_id, "volume_level": round(pct / 100, 2)},
        )
        await ctx.send(f"volume {entity_id} → {pct}%")
    except Exception as e:
        logger.error("vol error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 4: Run — verify pass**

```
pytest tests/test_commands.py -v -k "scene or play or pause or vol"
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add commands.py tests/test_commands.py
git commit -m "feat: scene/play/pause/vol command handlers"
```

---

### Task 8: commands.py — curtain, say, entities + TTSRateLimiter

**Files:**
- Modify: `commands.py` (append curtain, say, entities, TTSRateLimiter)
- Modify: `tests/test_commands.py` (append tests)

- [ ] **Step 1: Append failing tests to tests/test_commands.py**

```python
# --- curtain ---

async def test_curtain_open(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "open"])
    ha.call_service.assert_called_once_with(
        "cover", "open_cover", {"entity_id": "cover.blinds"}
    )


async def test_curtain_close(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "close"])
    ha.call_service.assert_called_once_with(
        "cover", "close_cover", {"entity_id": "cover.blinds"}
    )


async def test_curtain_stop(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "stop"])
    ha.call_service.assert_called_once_with(
        "cover", "stop_cover", {"entity_id": "cover.blinds"}
    )


async def test_curtain_bad_action(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "flip"])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]


# --- say ---

async def test_say_calls_tts(imports):
    from commands import cmd_say, TTSRateLimiter
    ctx = make_ctx()
    ha = make_ha()
    limiter = TTSRateLimiter(cooldown_sec=0)
    await cmd_say(ctx, ha, "tts.cloud_say", "media_player.speaker", limiter, "ch", ["hello", "world"])
    ha.call_service.assert_called_once_with(
        "tts", "cloud_say",
        {"entity_id": "media_player.speaker", "message": "hello world"}
    )


async def test_say_no_tts_entity(imports):
    from commands import cmd_say, TTSRateLimiter
    ctx = make_ctx()
    ha = make_ha()
    limiter = TTSRateLimiter(cooldown_sec=0)
    await cmd_say(ctx, ha, "tts.cloud_say", None, limiter, "ch", ["hello"])
    ctx.send.assert_called_once_with("TTS not configured")
    ha.call_service.assert_not_called()


async def test_say_cooldown_blocks(imports):
    from commands import cmd_say, TTSRateLimiter
    ctx = make_ctx()
    ha = make_ha()
    limiter = TTSRateLimiter(cooldown_sec=9999)
    # First call passes
    await cmd_say(ctx, ha, "tts.cloud_say", "media_player.speaker", limiter, "ch", ["hello"])
    # Second call blocked
    ctx2 = make_ctx()
    ha2 = make_ha()
    await cmd_say(ctx2, ha2, "tts.cloud_say", "media_player.speaker", limiter, "ch", ["hello"])
    ctx2.send.assert_called_once_with("TTS cooldown active")
    ha2.call_service.assert_not_called()


# --- entities ---

async def test_entities_lists_domain(imports):
    from commands import cmd_entities
    ctx = make_ctx()
    idx = EntityIndex()
    idx.build([
        {"entity_id": "light.lamp", "attributes": {"friendly_name": "Lamp"}},
    ])
    await cmd_entities(ctx, idx, ["light"])
    ctx.send.assert_called_once()
    assert "light.lamp" in ctx.send.call_args[0][0]


async def test_entities_no_args(imports):
    from commands import cmd_entities
    ctx = make_ctx()
    idx = EntityIndex()
    idx.build([])
    await cmd_entities(ctx, idx, [])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]
```

- [ ] **Step 2: Run — verify fail**

```
pytest tests/test_commands.py -v -k "curtain or say or entities"
```

Expected: `ImportError: cannot import name 'cmd_curtain'`

- [ ] **Step 3: Append to commands.py**

```python
_CURTAIN_ACTIONS = {
    "open": "open_cover",
    "close": "close_cover",
    "stop": "stop_cover",
}


async def cmd_curtain(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2 or args[1].lower() not in _CURTAIN_ACTIONS:
        await ctx.send("usage: !curtain <name> open|close|stop")
        return
    name, action = args[0], args[1].lower()
    entity_id = await _resolve(ctx, index, "cover", name)
    if not entity_id:
        return
    service = _CURTAIN_ACTIONS[action]
    try:
        await ha.call_service("cover", service, {"entity_id": entity_id})
        await ctx.send(f"curtain {entity_id} {action}")
    except Exception as e:
        logger.error("curtain error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


class TTSRateLimiter:
    def __init__(self, cooldown_sec: int) -> None:
        self._cooldown = cooldown_sec
        self._last: dict[str, float] = {}

    def check(self, channel: str) -> bool:
        now = time.monotonic()
        if now - self._last.get(channel, 0.0) < self._cooldown:
            return False
        self._last[channel] = now
        return True


async def cmd_say(
    ctx: ChatContext,
    ha: HAClient,
    tts_service: str,
    tts_entity: str | None,
    limiter: TTSRateLimiter,
    channel_name: str,
    args: list[str],
) -> None:
    if not tts_entity:
        await ctx.send("TTS not configured")
        return
    if not args:
        await ctx.send("usage: !say <text>")
        return
    if not limiter.check(channel_name):
        await ctx.send("TTS cooldown active")
        return
    domain, service = tts_service.split(".", 1)
    message = " ".join(args)
    try:
        await ha.call_service(
            domain, service, {"entity_id": tts_entity, "message": message}
        )
        await ctx.send(f"said: {message[:50]}")
    except Exception as e:
        logger.error("say error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_entities(
    ctx: ChatContext, index: EntityIndex, args: list[str]
) -> None:
    if not args:
        await ctx.send("usage: !entities <domain>")
        return
    domain = args[0].lower()
    ids = index.list_domain(domain)
    if not ids:
        await ctx.send(f"no {domain} entities found")
        return
    await ctx.send(f"{domain}: {', '.join(ids)}")
```

- [ ] **Step 4: Run all tests — verify pass**

```
pytest tests/ -v
```

Expected: all PASSED (no failures)

- [ ] **Step 5: Commit**

```bash
git add commands.py tests/test_commands.py
git commit -m "feat: curtain/say/entities handlers + TTSRateLimiter"
```

---

### Task 9: bot.py

**Files:**
- Create: `bot.py`

No unit tests for bot.py — twitchio integration is tested manually (smoke test in README). The components it wires together are already tested.

- [ ] **Step 1: Create bot.py**

```python
from __future__ import annotations
import asyncio
import logging
import logging.handlers
import sys

import aiohttp
from twitchio.ext import commands

import commands as cmd_module
from auth import is_allowed
from commands import TTSRateLimiter
from config import Config, load_config
from homeassistant import EntityIndex, HAClient

logger = logging.getLogger("bot")


def setup_logging(level: str) -> None:
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    root = logging.getLogger()
    root.setLevel(level)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.handlers.RotatingFileHandler(
        "bot.log", maxBytes=1_000_000, backupCount=5
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


class TwitchBot(commands.Bot):
    def __init__(
        self, cfg: Config, ha: HAClient, index: EntityIndex
    ) -> None:
        super().__init__(
            token=cfg.twitch_token,
            prefix=cfg.command_prefix,
            initial_channels=cfg.channels,
        )
        self._cfg = cfg
        self._ha = ha
        self._index = index
        self._limiter = TTSRateLimiter(cfg.tts_cooldown_sec)

    async def event_ready(self) -> None:
        logger.info(
            "ready nick=%s channels=%s", self.nick, self._cfg.channels
        )
        await self._refresh_index()
        asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cfg.entity_refresh_sec)
            await self._refresh_index()

    async def _refresh_index(self) -> None:
        try:
            states = await self._ha.get_states()
            self._index.build(states)
            total = sum(len(v) for v in self._index._index.values())
            logger.info("entity index refreshed count=%d", total)
        except Exception as e:
            logger.error("entity refresh failed: %s", e)

    def _gate(self, ctx: commands.Context) -> bool:
        if not is_allowed(ctx.author.name, self._cfg.allowed_users):
            logger.debug(
                "blocked user=%s channel=%s",
                ctx.author.name,
                ctx.channel.name,
            )
            return False
        return True

    def _log(self, ctx: commands.Context) -> None:
        logger.info(
            "channel=%s user=%s cmd=%s",
            ctx.channel.name,
            ctx.author.name,
            ctx.message.content.split()[0],
        )

    @commands.command(name="light")
    async def light(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_light(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="color")
    async def color(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_color(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="bright")
    async def bright(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_bright(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="scene")
    async def scene(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_scene(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_play(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_pause(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="vol")
    async def vol(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_vol(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="curtain")
    async def curtain(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_curtain(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_say(
            ctx,
            self._ha,
            self._cfg.tts_service,
            self._cfg.tts_entity,
            self._limiter,
            ctx.channel.name,
            list(args),
        )
        self._log(ctx)

    @commands.command(name="entities")
    async def entities(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_entities(ctx, self._index, list(args))
        self._log(ctx)


async def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)
    async with aiohttp.ClientSession() as session:
        ha = HAClient(cfg.ha_url, cfg.ha_token, session)
        index = EntityIndex()
        bot = TwitchBot(cfg, ha, index)
        await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Verify full test suite still passes**

```
pytest tests/ -v
```

Expected: all PASSED

- [ ] **Step 3: Commit**

```bash
git add bot.py
git commit -m "feat: twitchio bot wiring all commands"
```

---

### Task 10: README.md

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Twitch Home Assistant Bot

Controls Home Assistant from Twitch chat via Nabu Casa.

## Requirements

- Python 3.11+
- Nabu Casa subscription (or self-hosted HA with public URL)
- Twitch account for the bot + OAuth token

## Setup

### 1. Get a Twitch OAuth token

Go to https://twitchapps.com/tmi/ and log in as the bot account.
Copy the token (starts with `oauth:`).

### 2. Get a Home Assistant Long-Lived Access Token

In HA: Profile → Long-Lived Access Tokens → Create Token.

### 3. Configure

```bash
cp .env.example .env
# Edit .env with your values
```

Required fields in `.env`:

| Key | Value |
|---|---|
| `TWITCH_TOKEN` | `oauth:xxxx` from step 1 |
| `TWITCH_BOT_NICK` | Bot account username |
| `HA_URL` | `https://your-id.ui.nabu.casa` |
| `HA_TOKEN` | Long-lived token from step 2 |

Optional: set `TTS_ENTITY` to a `media_player.xxxx` entity_id to enable `!say`.

### 4. Install and run

```bash
pip install -r requirements.txt
python bot.py
```

Look for `ready nick=<botname>` in the log.

## Commands

All commands require the sender to be in `ALLOWED_USERS` (default: directorynetworks, JwsoatMedia, dylanwech, directorynetwork).

| Command | Example | Effect |
|---|---|---|
| `!light <name> on\|off` | `!light lamp on` | Turn light on or off |
| `!color <name> <color>` | `!color lamp red` | Set light color (CSS3 name) |
| `!bright <name> <0-100>` | `!bright lamp 50` | Set brightness % |
| `!scene <name>` | `!scene party` | Activate HA scene |
| `!play <name>` | `!play tv` | Play media player |
| `!pause <name>` | `!pause tv` | Pause media player |
| `!vol <name> <0-100>` | `!vol tv 30` | Set volume % |
| `!curtain <name> open\|close\|stop` | `!curtain blinds open` | Control cover/blind |
| `!say <text>` | `!say hello chat` | Speak via TTS |
| `!entities <domain>` | `!entities light` | List known entities |

Entity `<name>` is matched by friendly name or entity_id suffix (fuzzy, case-insensitive).

## Smoke test checklist

After starting the bot, run each from an allowed account in one of the joined channels:

- [ ] `!entities light` — bot replies with light entity IDs
- [ ] `!light <entity from above> on` — physical light turns on
- [ ] `!light <entity> off` — light turns off
- [ ] `!bright <entity> 50` — light dims to 50%
- [ ] `!color <entity> blue` — light turns blue
- [ ] `!entities scene` — bot replies with scene names
- [ ] `!scene <scene from above>` — HA scene activates
- [ ] `!entities media_player` — bot replies with media player IDs
- [ ] `!play <player>` — media player starts playing
- [ ] `!vol <player> 30` — volume set to 30%
- [ ] `!pause <player>` — media player pauses
- [ ] `!entities cover` — bot replies with cover IDs (if any)
- [ ] `!curtain <cover> open` — cover opens
- [ ] `!say hello from chat` — TTS speaks (requires `TTS_ENTITY` set)
- [ ] Non-allowed account: send `!light <entity> on` — no reply, no light change

## Logs

`bot.log` rotates at 1 MB, keeps 5 files. Format:
```
2026-05-25T14:23:11Z INFO  bot channel=directorynetworks user=dylanwech cmd=!light
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: setup guide and smoke test checklist"
```

---

### Task 11: Full test run + final verification

- [ ] **Step 1: Run full test suite**

```
pytest tests/ -v --tb=short
```

Expected: ALL PASSED, 0 failures, 0 errors.

- [ ] **Step 2: Verify bot starts cleanly with dummy .env**

Copy `.env.example` to `.env`, set fake values for all required fields. Run:

```
python bot.py
```

Expected: `SystemExit` or Twitch auth error (not a Python import/syntax error). This confirms imports and config loading work.

Remove the test `.env` after verifying.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: final verification pass"
```
