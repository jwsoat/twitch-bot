# Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a web dashboard (FastAPI + plain HTML/JS) for managing Twitch bot commands, with a separate Docker container sharing a SQLite volume with the bot.

**Architecture:** Two Docker services (`twitch-bot`, `dashboard`) share a named volume `bot_data` mounted at `/data/`. Bot reads from `/data/bot_data.db` on every command via `store.py`. Dashboard has full CRUD access via `dashboard/db.py`. No polling — bot re-reads SQLite per command, so changes take effect immediately.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, python-jose (JWT), SQLite (stdlib), plain HTML/JS (no build step), Docker Compose, GitHub Actions.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `store.py` | Create | Bot reads custom commands + HA overrides from SQLite |
| `dashboard/db.py` | Create | SQLite schema init + CRUD for both tables |
| `dashboard/app.py` | Create | FastAPI app: JWT auth + API routes |
| `dashboard/static/index.html` | Create | Single-page UI: login + two tabs |
| `dashboard/requirements.txt` | Create | FastAPI dependencies |
| `dashboard/Dockerfile` | Create | Dashboard container image |
| `config.py` | Modify | Add `db_path` field |
| `commands.py` | Modify | Add `reply_override` param to all cmd_* functions |
| `bot.py` | Modify | Check HA overrides + handle custom commands via `event_message` |
| `docker-compose.yml` | Modify | Add dashboard service + bot_data volume |
| `.github/workflows/dashboard.yml` | Create | Build + push dashboard image |
| `tests/test_store.py` | Create | Tests for store.py |
| `tests/test_dashboard_db.py` | Create | Tests for dashboard/db.py |

---

## Task 1: `store.py` — Bot-side SQLite reads

**Files:**
- Create: `store.py`
- Create: `tests/test_store.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_store.py`:

```python
import sqlite3
import pytest
from store import get_custom_commands, get_ha_override, CustomCommand, HAOverride


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", path)
    with sqlite3.connect(path) as con:
        con.execute("""CREATE TABLE custom_commands (
            name TEXT PRIMARY KEY, response TEXT NOT NULL,
            cooldown_sec INTEGER DEFAULT 0, restricted INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1
        )""")
        con.execute("""CREATE TABLE ha_commands (
            name TEXT PRIMARY KEY, alias TEXT, response_template TEXT,
            enabled INTEGER DEFAULT 1, allowed_users TEXT
        )""")
        con.commit()
    return path


def test_get_custom_commands_empty(db_path):
    assert get_custom_commands() == []


def test_get_custom_commands_returns_enabled_only(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO custom_commands VALUES ('discord','discord.gg/xyz',0,0,1)")
        con.execute("INSERT INTO custom_commands VALUES ('hidden','secret',0,0,0)")
        con.commit()
    result = get_custom_commands()
    assert len(result) == 1
    assert result[0].name == "discord"
    assert result[0].response == "discord.gg/xyz"
    assert result[0].restricted is False


def test_get_custom_commands_restricted_flag(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO custom_commands VALUES ('vip','vip only',0,1,1)")
        con.commit()
    result = get_custom_commands()
    assert result[0].restricted is True


def test_get_ha_override_default_when_missing(db_path):
    override = get_ha_override("light")
    assert override.enabled is True
    assert override.alias is None
    assert override.response_template is None
    assert override.allowed_users is None


def test_get_ha_override_reads_values(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO ha_commands VALUES ('light','l','Lit!',1,NULL)")
        con.commit()
    override = get_ha_override("light")
    assert override.alias == "l"
    assert override.response_template == "Lit!"
    assert override.enabled is True


def test_get_ha_override_disabled(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO ha_commands VALUES ('scene',NULL,NULL,0,NULL)")
        con.commit()
    assert get_ha_override("scene").enabled is False


def test_get_ha_override_allowed_users(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO ha_commands VALUES ('curtain',NULL,NULL,1,'[\"user1\",\"user2\"]')")
        con.commit()
    override = get_ha_override("curtain")
    assert override.allowed_users == ["user1", "user2"]


def test_get_custom_commands_missing_db(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/nonexistent/path.db")
    assert get_custom_commands() == []


def test_get_ha_override_missing_db(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/nonexistent/path.db")
    override = get_ha_override("light")
    assert override.enabled is True  # safe default
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```
.venv/Scripts/pytest tests/test_store.py -v
```
Expected: `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 3: Create `store.py`**

```python
from __future__ import annotations
import json
import os
import sqlite3
from dataclasses import dataclass
from typing import Optional


@dataclass
class CustomCommand:
    name: str
    response: str
    cooldown_sec: int
    restricted: bool
    enabled: bool


@dataclass
class HAOverride:
    name: str
    alias: Optional[str]
    response_template: Optional[str]
    enabled: bool
    allowed_users: Optional[list[str]]  # None = use global allowlist


def _db_path() -> str:
    return os.environ.get("DB_PATH", "/data/bot_data.db")


def get_custom_commands() -> list[CustomCommand]:
    try:
        with sqlite3.connect(_db_path()) as con:
            rows = con.execute(
                "SELECT name, response, cooldown_sec, restricted, enabled "
                "FROM custom_commands WHERE enabled = 1"
            ).fetchall()
        return [
            CustomCommand(
                name=r[0], response=r[1], cooldown_sec=r[2],
                restricted=bool(r[3]), enabled=bool(r[4]),
            )
            for r in rows
        ]
    except Exception:
        return []


def get_ha_override(name: str) -> HAOverride:
    try:
        with sqlite3.connect(_db_path()) as con:
            row = con.execute(
                "SELECT name, alias, response_template, enabled, allowed_users "
                "FROM ha_commands WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            return HAOverride(name=name, alias=None, response_template=None,
                              enabled=True, allowed_users=None)
        users = json.loads(row[4]) if row[4] else None
        return HAOverride(
            name=row[0], alias=row[1], response_template=row[2],
            enabled=bool(row[3]), allowed_users=users,
        )
    except Exception:
        return HAOverride(name=name, alias=None, response_template=None,
                          enabled=True, allowed_users=None)
```

- [ ] **Step 4: Run tests — expect PASS**

```
.venv/Scripts/pytest tests/test_store.py -v
```
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat: add store.py for bot-side SQLite reads"
```

---

## Task 2: `dashboard/db.py` — SQLite CRUD + schema

**Files:**
- Create: `dashboard/__init__.py`
- Create: `dashboard/db.py`
- Create: `tests/test_dashboard_db.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_dashboard_db.py`:

```python
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
import db as dashboard_db
from db import (
    init_db, list_custom_commands, create_custom_command,
    update_custom_command, delete_custom_command,
    list_ha_commands, update_ha_command, BUILTIN_HA_COMMANDS,
)


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    init_db(path)
    return path


def test_init_creates_all_ha_commands(db_path):
    ha = list_ha_commands(db_path)
    assert {r["name"] for r in ha} == set(BUILTIN_HA_COMMANDS)


def test_init_idempotent(db_path):
    init_db(db_path)
    assert len(list_ha_commands(db_path)) == len(BUILTIN_HA_COMMANDS)


def test_ha_commands_default_enabled(db_path):
    ha = list_ha_commands(db_path)
    assert all(r["enabled"] for r in ha)


def test_create_and_list_custom_command(db_path):
    create_custom_command(db_path, {
        "name": "discord", "response": "discord.gg/xyz",
        "cooldown_sec": 0, "restricted": 0, "enabled": 1,
    })
    cmds = list_custom_commands(db_path)
    assert len(cmds) == 1
    assert cmds[0]["name"] == "discord"
    assert cmds[0]["response"] == "discord.gg/xyz"


def test_update_custom_command(db_path):
    create_custom_command(db_path, {
        "name": "discord", "response": "old",
        "cooldown_sec": 0, "restricted": 0, "enabled": 1,
    })
    update_custom_command(db_path, "discord", {
        "response": "new", "cooldown_sec": 5, "restricted": 0, "enabled": 1,
    })
    cmds = list_custom_commands(db_path)
    assert cmds[0]["response"] == "new"
    assert cmds[0]["cooldown_sec"] == 5


def test_delete_custom_command(db_path):
    create_custom_command(db_path, {
        "name": "discord", "response": "x",
        "cooldown_sec": 0, "restricted": 0, "enabled": 1,
    })
    delete_custom_command(db_path, "discord")
    assert list_custom_commands(db_path) == []


def test_update_ha_command_alias(db_path):
    update_ha_command(db_path, "light", {
        "alias": "l", "response_template": "Lit!", "enabled": 1, "allowed_users": [],
    })
    ha = list_ha_commands(db_path)
    light = next(r for r in ha if r["name"] == "light")
    assert light["alias"] == "l"
    assert light["response_template"] == "Lit!"


def test_update_ha_command_allowed_users(db_path):
    update_ha_command(db_path, "curtain", {
        "alias": None, "response_template": None,
        "enabled": 1, "allowed_users": ["user1", "user2"],
    })
    ha = list_ha_commands(db_path)
    curtain = next(r for r in ha if r["name"] == "curtain")
    assert curtain["allowed_users"] == ["user1", "user2"]


def test_update_ha_command_disable(db_path):
    update_ha_command(db_path, "scene", {
        "alias": None, "response_template": None, "enabled": 0, "allowed_users": [],
    })
    ha = list_ha_commands(db_path)
    scene = next(r for r in ha if r["name"] == "scene")
    assert scene["enabled"] == 0
```

- [ ] **Step 2: Run tests — expect FAIL**

```
.venv/Scripts/pytest tests/test_dashboard_db.py -v
```
Expected: `ModuleNotFoundError`

- [ ] **Step 3: Create `dashboard/__init__.py`** (empty file)

- [ ] **Step 4: Create `dashboard/db.py`**

```python
from __future__ import annotations
import json
import sqlite3

BUILTIN_HA_COMMANDS = [
    "light", "color", "bright", "scene",
    "play", "pause", "vol", "curtain", "say", "entities",
]


def init_db(db_path: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS custom_commands (
                name         TEXT PRIMARY KEY,
                response     TEXT NOT NULL,
                cooldown_sec INTEGER DEFAULT 0,
                restricted   INTEGER DEFAULT 0,
                enabled      INTEGER DEFAULT 1
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS ha_commands (
                name              TEXT PRIMARY KEY,
                alias             TEXT,
                response_template TEXT,
                enabled           INTEGER DEFAULT 1,
                allowed_users     TEXT
            )
        """)
        for cmd in BUILTIN_HA_COMMANDS:
            con.execute(
                "INSERT OR IGNORE INTO ha_commands (name) VALUES (?)", (cmd,)
            )
        con.commit()


def list_custom_commands(db_path: str) -> list[dict]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM custom_commands ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def create_custom_command(db_path: str, data: dict) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            "INSERT INTO custom_commands "
            "(name, response, cooldown_sec, restricted, enabled) "
            "VALUES (:name, :response, :cooldown_sec, :restricted, :enabled)",
            data,
        )
        con.commit()


def update_custom_command(db_path: str, name: str, data: dict) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE custom_commands SET response=:response, "
            "cooldown_sec=:cooldown_sec, restricted=:restricted, "
            "enabled=:enabled WHERE name=:name",
            {**data, "name": name},
        )
        con.commit()


def delete_custom_command(db_path: str, name: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("DELETE FROM custom_commands WHERE name = ?", (name,))
        con.commit()


def list_ha_commands(db_path: str) -> list[dict]:
    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT * FROM ha_commands ORDER BY name"
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["allowed_users"] = json.loads(d["allowed_users"]) if d["allowed_users"] else []
        result.append(d)
    return result


def update_ha_command(db_path: str, name: str, data: dict) -> None:
    users = data.get("allowed_users")
    users_json = json.dumps(users) if users else None
    with sqlite3.connect(db_path) as con:
        con.execute(
            "UPDATE ha_commands SET alias=:alias, "
            "response_template=:response_template, "
            "enabled=:enabled, allowed_users=:allowed_users WHERE name=:name",
            {
                "alias": data.get("alias") or None,
                "response_template": data.get("response_template") or None,
                "enabled": int(data.get("enabled", 1)),
                "allowed_users": users_json,
                "name": name,
            },
        )
        con.commit()
```

- [ ] **Step 5: Run tests — expect PASS**

```
.venv/Scripts/pytest tests/test_dashboard_db.py -v
```
Expected: `11 passed`

- [ ] **Step 6: Commit**

```bash
git add dashboard/__init__.py dashboard/db.py tests/test_dashboard_db.py
git commit -m "feat: add dashboard/db.py SQLite CRUD + schema init"
```

---

## Task 3: `config.py` — Add `db_path`

**Files:**
- Modify: `config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_config.py`:

```python
def test_db_path_default(monkeypatch):
    for key in ("TWITCH_TOKEN", "TWITCH_BOT_NICK", "HA_URL", "HA_TOKEN"):
        monkeypatch.setenv(key, "x")
    monkeypatch.delenv("DB_PATH", raising=False)
    from config import load_config
    cfg = load_config()
    assert cfg.db_path == "/data/bot_data.db"


def test_db_path_custom(monkeypatch):
    for key in ("TWITCH_TOKEN", "TWITCH_BOT_NICK", "HA_URL", "HA_TOKEN"):
        monkeypatch.setenv(key, "x")
    monkeypatch.setenv("DB_PATH", "/tmp/mydb.db")
    from config import load_config
    cfg = load_config()
    assert cfg.db_path == "/tmp/mydb.db"
```

- [ ] **Step 2: Run — expect FAIL**

```
.venv/Scripts/pytest tests/test_config.py::test_db_path_default -v
```
Expected: `AttributeError: 'Config' object has no attribute 'db_path'`

- [ ] **Step 3: Update `config.py`**

Add `db_path: str` to the `Config` dataclass and `db_path=os.getenv("DB_PATH", "/data/bot_data.db")` to `load_config()`:

```python
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
    db_path: str          # NEW
```

In `load_config()`, add at the end of the `Config(...)` call:

```python
        db_path=os.getenv("DB_PATH", "/data/bot_data.db"),
```

- [ ] **Step 4: Run — expect PASS**

```
.venv/Scripts/pytest tests/test_config.py -v
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add db_path to Config"
```

---

## Task 4: `commands.py` — Add `reply_override` to cmd_* functions

Each cmd_* function gets an optional `reply_override: str | None = None` param. When set, it replaces the default success reply sent to chat.

**Files:**
- Modify: `commands.py`

The pattern for every function: replace `await ctx.send(f"...")` success lines with:

```python
await ctx.send(reply_override if reply_override is not None else f"default message")
```

- [ ] **Step 1: Update `cmd_light`**

Change signature and success sends:

```python
async def cmd_light(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
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
        await ctx.send(reply_override if reply_override is not None else f"light {entity_id} {state}")
    except Exception as e:
        logger.error("light error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 2: Update `cmd_color`**

```python
async def cmd_color(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
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
        await ctx.send(reply_override if reply_override is not None else f"light {entity_id} color → {color}")
    except Exception as e:
        logger.error("color error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 3: Update `cmd_bright`**

```python
async def cmd_bright(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
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
        await ctx.send(reply_override if reply_override is not None else f"light {entity_id} brightness → {pct}%")
    except Exception as e:
        logger.error("bright error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 4: Update `cmd_scene`**

```python
async def cmd_scene(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
) -> None:
    if not args:
        await ctx.send("usage: !scene <name>")
        return
    entity_id = await _resolve(ctx, index, "scene", args[0])
    if not entity_id:
        return
    try:
        await ha.call_service("scene", "turn_on", {"entity_id": entity_id})
        await ctx.send(reply_override if reply_override is not None else f"scene {entity_id} activated")
    except Exception as e:
        logger.error("scene error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 5: Update `cmd_play`, `cmd_pause`**

```python
async def cmd_play(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
) -> None:
    if not args:
        await ctx.send("usage: !play <name>")
        return
    entity_id = await _resolve(ctx, index, "media_player", args[0])
    if not entity_id:
        return
    try:
        await ha.call_service("media_player", "media_play", {"entity_id": entity_id})
        await ctx.send(reply_override if reply_override is not None else f"playing {entity_id}")
    except Exception as e:
        logger.error("play error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_pause(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
) -> None:
    if not args:
        await ctx.send("usage: !pause <name>")
        return
    entity_id = await _resolve(ctx, index, "media_player", args[0])
    if not entity_id:
        return
    try:
        await ha.call_service("media_player", "media_pause", {"entity_id": entity_id})
        await ctx.send(reply_override if reply_override is not None else f"paused {entity_id}")
    except Exception as e:
        logger.error("pause error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 6: Update `cmd_vol`**

```python
async def cmd_vol(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
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
            "media_player", "volume_set",
            {"entity_id": entity_id, "volume_level": round(pct / 100, 2)},
        )
        await ctx.send(reply_override if reply_override is not None else f"volume {entity_id} → {pct}%")
    except Exception as e:
        logger.error("vol error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 7: Update `cmd_curtain`**

```python
async def cmd_curtain(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
) -> None:
    if not args:
        await ctx.send("usage: !curtain open|close|stop|<0-100>")
        return
    arg = args[0].lower()
    entity_ids = index.list_domain("cover", limit=50)
    if not entity_ids:
        await ctx.send("no cover entities found")
        return
    try:
        if arg in _CURTAIN_ACTIONS:
            service = _CURTAIN_ACTIONS[arg]
            await ha.call_service("cover", service, {"entity_id": entity_ids})
            await ctx.send(reply_override if reply_override is not None else f"curtains {arg}")
        else:
            pos = max(0, min(100, int(arg)))
            await ha.call_service(
                "cover", "set_cover_position",
                {"entity_id": entity_ids, "position": pos},
            )
            await ctx.send(reply_override if reply_override is not None else f"curtains → {pos}%")
    except ValueError:
        await ctx.send("usage: !curtain open|close|stop|<0-100>")
    except Exception as e:
        logger.error("curtain error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
```

- [ ] **Step 8: Update `cmd_entities`**

```python
async def cmd_entities(
    ctx: ChatContext, index: EntityIndex, args: list[str],
    reply_override: str | None = None,
) -> None:
    if not args:
        await ctx.send("usage: !entities <domain>")
        return
    domain = args[0].lower()
    ids = index.list_domain(domain)
    if not ids:
        await ctx.send(f"no {domain} entities found")
        return
    await ctx.send(reply_override if reply_override is not None else f"{domain}: {', '.join(ids)}")
```

Note: `cmd_say` does NOT get `reply_override` — TTS response is always "said: {message}".

- [ ] **Step 9: Run full test suite — expect all pass**

```
.venv/Scripts/pytest -v
```
Expected: all existing tests pass (reply_override defaults to None, no behaviour change).

- [ ] **Step 10: Commit**

```bash
git add commands.py
git commit -m "feat: add reply_override param to cmd_* functions for dashboard overrides"
```

---

## Task 5: `bot.py` — HA overrides + custom command handling

**Files:**
- Modify: `bot.py`

- [ ] **Step 1: Add `store` import and `event_message` to `bot.py`**

Add at top of `bot.py`:

```python
import store
```

- [ ] **Step 2: Add `_custom_limiters` dict and `event_message` override**

Add to `TwitchBot.__init__`:

```python
        self._custom_limiters: dict[str, TTSRateLimiter] = {}
```

Add after `__init__`:

```python
    async def event_message(self, message) -> None:
        if message.echo:
            return
        content = message.content or ""
        if content.startswith(self._cfg.command_prefix):
            cmd_name = content[len(self._cfg.command_prefix):].split()[0].lower()
            customs = store.get_custom_commands()
            for cc in customs:
                if cc.name.lower() == cmd_name:
                    if cc.restricted and not is_allowed(
                        message.author.name, self._cfg.allowed_users
                    ):
                        return
                    if cc.cooldown_sec > 0:
                        if cc.name not in self._custom_limiters:
                            self._custom_limiters[cc.name] = TTSRateLimiter(cc.cooldown_sec)
                        if not self._custom_limiters[cc.name].check(message.channel.name):
                            return
                    await message.channel.send(cc.response)
                    return
        await self.handle_commands(message)
```

- [ ] **Step 3: Add `_check_override` helper and update each command handler**

Add helper method to `TwitchBot`:

```python
    def _check_override(self, name: str, ctx) -> tuple[bool, str | None]:
        """Returns (enabled, reply_override). Checks per-command allowed_users if set."""
        override = store.get_ha_override(name)
        if not override.enabled:
            return False, None
        if override.allowed_users is not None:
            if not is_allowed(ctx.author.name, set(override.allowed_users)):
                return False, None
        return True, override.response_template
```

- [ ] **Step 4: Update each command handler in `TwitchBot` to use `_check_override`**

Replace each handler body. Pattern (shown for `light`, repeat for all 10):

```python
    @commands.command(name="light")
    async def light(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("light", ctx)
        if not enabled:
            return
        await cmd_module.cmd_light(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="color")
    async def color(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("color", ctx)
        if not enabled:
            return
        await cmd_module.cmd_color(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="bright")
    async def bright(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("bright", ctx)
        if not enabled:
            return
        await cmd_module.cmd_bright(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="scene")
    async def scene(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("scene", ctx)
        if not enabled:
            return
        await cmd_module.cmd_scene(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("play", ctx)
        if not enabled:
            return
        await cmd_module.cmd_play(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("pause", ctx)
        if not enabled:
            return
        await cmd_module.cmd_pause(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="vol")
    async def vol(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("vol", ctx)
        if not enabled:
            return
        await cmd_module.cmd_vol(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="curtain")
    async def curtain(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("curtain", ctx)
        if not enabled:
            return
        await cmd_module.cmd_curtain(ctx, self._ha, self._index, list(args), reply_override=reply)
        self._log(ctx)

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, _ = self._check_override("say", ctx)
        if not enabled:
            return
        await cmd_module.cmd_say(
            ctx, self._ha, self._cfg.tts_service, self._cfg.tts_entity,
            self._limiter, ctx.channel.name, list(args),
        )
        self._log(ctx)

    @commands.command(name="entities")
    async def entities(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        enabled, reply = self._check_override("entities", ctx)
        if not enabled:
            return
        await cmd_module.cmd_entities(ctx, self._index, list(args), reply_override=reply)
        self._log(ctx)
```

- [ ] **Step 5: Run full test suite**

```
.venv/Scripts/pytest -v
```
Expected: all existing tests pass.

- [ ] **Step 6: Commit**

```bash
git add bot.py
git commit -m "feat: bot checks HA overrides and handles custom commands via event_message"
```

---

## Task 6: `dashboard/app.py` — FastAPI + JWT auth + API

**Files:**
- Create: `dashboard/app.py`
- Create: `dashboard/requirements.txt`

- [ ] **Step 1: Create `dashboard/requirements.txt`**

```
fastapi>=0.111,<1
uvicorn[standard]>=0.29,<1
python-jose[cryptography]>=3.3,<4
pydantic>=2.0,<3
```

- [ ] **Step 2: Install into venv for local testing**

```
.venv/Scripts/pip install fastapi uvicorn "python-jose[cryptography]" pydantic
```

- [ ] **Step 3: Create `dashboard/app.py`**

```python
from __future__ import annotations
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

# Allow importing db from same directory
sys.path.insert(0, os.path.dirname(__file__))
import db as dashboard_db

DB_PATH = os.environ.get("DB_PATH", "/data/bot_data.db")
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")
_SECRET_KEY = DASHBOARD_PASSWORD + "_twitch_bot_jwt_v1"
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24

dashboard_db.init_db(DB_PATH)

app = FastAPI(title="Twitch Bot Dashboard")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, _SECRET_KEY, algorithm=_ALGORITHM)


def _current_user(token: Annotated[str, Depends(_oauth2)]) -> str:
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return username
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


class Token(BaseModel):
    access_token: str
    token_type: str


@app.post("/auth/token", response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user_ok = secrets.compare_digest(form_data.username, DASHBOARD_USER)
    pass_ok = secrets.compare_digest(form_data.password, DASHBOARD_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return Token(access_token=_create_token(form_data.username), token_type="bearer")


# --- Custom commands ---

@app.get("/api/custom")
async def list_custom(_: Annotated[str, Depends(_current_user)]) -> list[dict]:
    return dashboard_db.list_custom_commands(DB_PATH)


class CustomCommandIn(BaseModel):
    name: str
    response: str
    cooldown_sec: int = 0
    restricted: bool = False
    enabled: bool = True


@app.post("/api/custom", status_code=201)
async def create_custom(
    cmd: CustomCommandIn,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.create_custom_command(DB_PATH, cmd.model_dump())
    return {"ok": True}


class CustomCommandUpdate(BaseModel):
    response: str
    cooldown_sec: int = 0
    restricted: bool = False
    enabled: bool = True


@app.put("/api/custom/{name}")
async def update_custom(
    name: str,
    cmd: CustomCommandUpdate,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.update_custom_command(DB_PATH, name, cmd.model_dump())
    return {"ok": True}


@app.delete("/api/custom/{name}")
async def delete_custom(
    name: str,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.delete_custom_command(DB_PATH, name)
    return {"ok": True}


# --- HA commands ---

@app.get("/api/ha")
async def list_ha(_: Annotated[str, Depends(_current_user)]) -> list[dict]:
    return dashboard_db.list_ha_commands(DB_PATH)


class HACommandUpdate(BaseModel):
    alias: str | None = None
    response_template: str | None = None
    enabled: bool = True
    allowed_users: list[str] = []


@app.put("/api/ha/{name}")
async def update_ha(
    name: str,
    cmd: HACommandUpdate,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.update_ha_command(DB_PATH, name, cmd.model_dump())
    return {"ok": True}


# Serve static files last (catches all unmatched routes)
app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
```

- [ ] **Step 4: Write API tests**

Create `tests/test_dashboard_app.py`:

```python
import sys
import os
import pytest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))


@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "test.db")
    import dashboard.db as ddb
    ddb.init_db(db)
    import dashboard.app as app_module
    # Patch module-level vars directly
    app_module.DB_PATH = db
    app_module.DASHBOARD_USER = "admin"
    app_module.DASHBOARD_PASSWORD = "secret"
    app_module._SECRET_KEY = "secret_twitch_bot_jwt_v1"
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def get_token(client):
    res = client.post("/auth/token", data={"username": "admin", "password": "secret"})
    return res.json()["access_token"]


def test_login_success(client):
    res = client.post("/auth/token", data={"username": "admin", "password": "secret"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client):
    res = client.post("/auth/token", data={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_list_custom_requires_auth(client):
    res = client.get("/api/custom")
    assert res.status_code == 401


def test_create_and_list_custom(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/custom", json={
        "name": "discord", "response": "discord.gg/xyz",
        "cooldown_sec": 0, "restricted": False, "enabled": True,
    }, headers=headers)
    res = client.get("/api/custom", headers=headers)
    assert res.status_code == 200
    assert res.json()[0]["name"] == "discord"


def test_delete_custom(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/custom", json={
        "name": "discord", "response": "x",
        "cooldown_sec": 0, "restricted": False, "enabled": True,
    }, headers=headers)
    client.delete("/api/custom/discord", headers=headers)
    res = client.get("/api/custom", headers=headers)
    assert res.json() == []


def test_list_ha_returns_all_builtins(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/ha", headers=headers)
    names = {r["name"] for r in res.json()}
    assert "light" in names
    assert "curtain" in names


def test_update_ha_command(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/ha/light", json={
        "alias": "l", "response_template": "Lit!",
        "enabled": True, "allowed_users": [],
    }, headers=headers)
    res = client.get("/api/ha", headers=headers)
    light = next(r for r in res.json() if r["name"] == "light")
    assert light["alias"] == "l"
```

- [ ] **Step 5: Install httpx (needed by FastAPI TestClient)**

```
.venv/Scripts/pip install httpx
```

- [ ] **Step 6: Run API tests**

```
.venv/Scripts/pytest tests/test_dashboard_app.py -v
```
Expected: `8 passed`

- [ ] **Step 7: Commit**

```bash
git add dashboard/app.py dashboard/requirements.txt tests/test_dashboard_app.py
git commit -m "feat: add dashboard FastAPI app with JWT auth and CRUD API"
```

---

## Task 7: `dashboard/static/index.html` — UI

**Files:**
- Create: `dashboard/static/index.html`

- [ ] **Step 1: Create `dashboard/static/` directory** (no content needed)

- [ ] **Step 2: Create `dashboard/static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Twitch Bot Dashboard</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0e0e10; color: #efeff1; min-height: 100vh; }
  #login-page { display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { background: #18181b; border-radius: 8px; padding: 2rem; width: 320px; }
  .card h1 { font-size: 1.25rem; margin-bottom: 1.5rem; color: #bf94ff; }
  input { width: 100%; padding: 0.5rem 0.75rem; margin-bottom: 0.75rem; background: #26262c;
          border: 1px solid #3a3a3f; border-radius: 4px; color: #efeff1; font-size: 0.9rem; }
  button { padding: 0.5rem 1rem; border: none; border-radius: 4px; cursor: pointer; font-size: 0.9rem; }
  .btn-primary { background: #bf94ff; color: #0e0e10; font-weight: 600; }
  .btn-primary:hover { background: #a970ff; }
  .btn-danger { background: #eb0400; color: #fff; }
  .btn-small { padding: 0.25rem 0.6rem; font-size: 0.8rem; }
  .btn-save { background: #00b894; color: #fff; }
  .error { color: #eb0400; font-size: 0.85rem; margin-top: 0.5rem; }
  #dashboard-page { display: none; }
  .header { background: #18181b; padding: 1rem 2rem; display: flex; align-items: center; justify-content: space-between; }
  .header h1 { color: #bf94ff; font-size: 1.1rem; }
  .tabs { display: flex; gap: 0; border-bottom: 2px solid #26262c; padding: 0 2rem; background: #18181b; }
  .tab-btn { padding: 0.75rem 1.5rem; background: none; border: none; color: #adadb8; cursor: pointer;
             border-bottom: 2px solid transparent; margin-bottom: -2px; font-size: 0.95rem; }
  .tab-btn.active { color: #bf94ff; border-bottom-color: #bf94ff; }
  .tab-content { padding: 2rem; }
  table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
  th { text-align: left; padding: 0.6rem 0.75rem; background: #26262c; color: #adadb8; font-weight: 500; }
  td { padding: 0.5rem 0.75rem; border-bottom: 1px solid #26262c; vertical-align: middle; }
  td input, td select { background: #26262c; border: 1px solid #3a3a3f; border-radius: 4px;
                         color: #efeff1; padding: 0.3rem 0.5rem; font-size: 0.85rem; width: 100%; }
  .add-row { margin-bottom: 1rem; }
  .status { font-size: 0.8rem; color: #adadb8; margin-top: 1rem; }
</style>
</head>
<body>

<!-- LOGIN -->
<div id="login-page">
  <div class="card">
    <h1>🤖 Bot Dashboard</h1>
    <form id="login-form">
      <input type="text" id="username" placeholder="Username" required>
      <input type="password" id="password" placeholder="Password" required>
      <button type="submit" class="btn-primary" style="width:100%">Login</button>
      <p class="error" id="login-error" style="display:none">Invalid credentials</p>
    </form>
  </div>
</div>

<!-- DASHBOARD -->
<div id="dashboard-page">
  <div class="header">
    <h1>🤖 Twitch Bot Dashboard</h1>
    <button class="btn-primary btn-small" onclick="logout()">Logout</button>
  </div>
  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('custom', this)">Custom Commands</button>
    <button class="tab-btn" onclick="switchTab('ha', this)">HA Commands</button>
  </div>

  <!-- CUSTOM COMMANDS TAB -->
  <div id="tab-custom" class="tab-content">
    <div class="add-row">
      <button class="btn-primary btn-small" onclick="addCustomRow()">+ Add Command</button>
    </div>
    <table>
      <thead><tr>
        <th>Command</th><th>Response</th><th>Cooldown (s)</th>
        <th>Restricted</th><th>Enabled</th><th>Actions</th>
      </tr></thead>
      <tbody id="custom-tbody"></tbody>
    </table>
    <p class="status" id="custom-status"></p>
  </div>

  <!-- HA COMMANDS TAB -->
  <div id="tab-ha" class="tab-content" style="display:none">
    <table>
      <thead><tr>
        <th>Command</th><th>Alias</th><th>Custom Response</th>
        <th>Allowed Users</th><th>Enabled</th><th></th>
      </tr></thead>
      <tbody id="ha-tbody"></tbody>
    </table>
    <p class="status" id="ha-status"></p>
  </div>
</div>

<script>
let token = localStorage.getItem('bot_token');

function api(method, path, body) {
  return fetch(path, {
    method,
    headers: {
      'Authorization': 'Bearer ' + token,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function showPage() {
  if (token) {
    document.getElementById('login-page').style.display = 'none';
    document.getElementById('dashboard-page').style.display = 'block';
    loadCustomCommands();
  } else {
    document.getElementById('login-page').style.display = 'flex';
    document.getElementById('dashboard-page').style.display = 'none';
  }
}

function logout() {
  localStorage.removeItem('bot_token');
  token = null;
  showPage();
}

document.getElementById('login-form').onsubmit = async (e) => {
  e.preventDefault();
  const body = new URLSearchParams({
    username: document.getElementById('username').value,
    password: document.getElementById('password').value,
  });
  const res = await fetch('/auth/token', { method: 'POST', body });
  if (res.ok) {
    token = (await res.json()).access_token;
    localStorage.setItem('bot_token', token);
    document.getElementById('login-error').style.display = 'none';
    showPage();
  } else {
    document.getElementById('login-error').style.display = 'block';
  }
};

function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-custom').style.display = name === 'custom' ? 'block' : 'none';
  document.getElementById('tab-ha').style.display = name === 'ha' ? 'block' : 'none';
  if (name === 'ha') loadHACommands();
}

// --- CUSTOM COMMANDS ---

async function loadCustomCommands() {
  const res = await api('GET', '/api/custom');
  if (res.status === 401) { logout(); return; }
  const cmds = await res.json();
  const tbody = document.getElementById('custom-tbody');
  tbody.innerHTML = '';
  cmds.forEach(cmd => tbody.appendChild(customRow(cmd)));
}

function customRow(cmd) {
  const tr = document.createElement('tr');
  tr.dataset.name = cmd.name;
  tr.innerHTML = `
    <td>!<strong>${cmd.name}</strong></td>
    <td><input type="text" value="${esc(cmd.response)}" class="c-response"></td>
    <td><input type="number" value="${cmd.cooldown_sec}" min="0" style="width:70px" class="c-cooldown"></td>
    <td><input type="checkbox" class="c-restricted" ${cmd.restricted ? 'checked' : ''}></td>
    <td><input type="checkbox" class="c-enabled" ${cmd.enabled ? 'checked' : ''}></td>
    <td>
      <button class="btn-save btn-small" onclick="saveCustom(this)">Save</button>
      <button class="btn-danger btn-small" onclick="deleteCustom(this)" style="margin-left:4px">Del</button>
    </td>`;
  return tr;
}

function addCustomRow() {
  const tr = document.createElement('tr');
  tr.dataset.name = '';
  tr.innerHTML = `
    <td>!<input type="text" placeholder="name" class="c-name" style="width:90px"></td>
    <td><input type="text" placeholder="response text" class="c-response"></td>
    <td><input type="number" value="0" min="0" style="width:70px" class="c-cooldown"></td>
    <td><input type="checkbox" class="c-restricted"></td>
    <td><input type="checkbox" class="c-enabled" checked></td>
    <td>
      <button class="btn-save btn-small" onclick="createCustom(this)">Add</button>
      <button class="btn-small" onclick="this.closest('tr').remove()" style="background:#3a3a3f;color:#efeff1;margin-left:4px">Cancel</button>
    </td>`;
  document.getElementById('custom-tbody').prepend(tr);
}

async function createCustom(btn) {
  const tr = btn.closest('tr');
  const name = tr.querySelector('.c-name').value.trim().toLowerCase().replace(/^!/, '');
  if (!name) { alert('Command name required'); return; }
  const body = {
    name,
    response: tr.querySelector('.c-response').value,
    cooldown_sec: parseInt(tr.querySelector('.c-cooldown').value) || 0,
    restricted: tr.querySelector('.c-restricted').checked,
    enabled: tr.querySelector('.c-enabled').checked,
  };
  const res = await api('POST', '/api/custom', body);
  if (res.ok) { status('custom', 'Saved!'); loadCustomCommands(); }
  else { status('custom', 'Error saving'); }
}

async function saveCustom(btn) {
  const tr = btn.closest('tr');
  const name = tr.dataset.name;
  const body = {
    response: tr.querySelector('.c-response').value,
    cooldown_sec: parseInt(tr.querySelector('.c-cooldown').value) || 0,
    restricted: tr.querySelector('.c-restricted').checked,
    enabled: tr.querySelector('.c-enabled').checked,
  };
  const res = await api('PUT', '/api/custom/' + name, body);
  status('custom', res.ok ? 'Saved!' : 'Error saving');
}

async function deleteCustom(btn) {
  const tr = btn.closest('tr');
  if (!confirm('Delete !' + tr.dataset.name + '?')) return;
  const res = await api('DELETE', '/api/custom/' + tr.dataset.name);
  if (res.ok) { tr.remove(); status('custom', 'Deleted'); }
}

// --- HA COMMANDS ---

async function loadHACommands() {
  const res = await api('GET', '/api/ha');
  if (res.status === 401) { logout(); return; }
  const cmds = await res.json();
  const tbody = document.getElementById('ha-tbody');
  tbody.innerHTML = '';
  cmds.forEach(cmd => tbody.appendChild(haRow(cmd)));
}

function haRow(cmd) {
  const tr = document.createElement('tr');
  tr.dataset.name = cmd.name;
  const users = (cmd.allowed_users || []).join(', ');
  tr.innerHTML = `
    <td><strong>!${cmd.name}</strong></td>
    <td><input type="text" value="${esc(cmd.alias || '')}" placeholder="(default)" class="ha-alias"></td>
    <td><input type="text" value="${esc(cmd.response_template || '')}" placeholder="(default)" class="ha-response"></td>
    <td><input type="text" value="${esc(users)}" placeholder="(global list)" class="ha-users"></td>
    <td><input type="checkbox" class="ha-enabled" ${cmd.enabled ? 'checked' : ''}></td>
    <td><button class="btn-save btn-small" onclick="saveHA(this)">Save</button></td>`;
  return tr;
}

async function saveHA(btn) {
  const tr = btn.closest('tr');
  const name = tr.dataset.name;
  const usersRaw = tr.querySelector('.ha-users').value.trim();
  const users = usersRaw ? usersRaw.split(',').map(u => u.trim()).filter(Boolean) : [];
  const body = {
    alias: tr.querySelector('.ha-alias').value.trim() || null,
    response_template: tr.querySelector('.ha-response').value.trim() || null,
    enabled: tr.querySelector('.ha-enabled').checked,
    allowed_users: users,
  };
  const res = await api('PUT', '/api/ha/' + name, body);
  status('ha', res.ok ? 'Saved!' : 'Error saving');
}

function status(tab, msg) {
  const el = document.getElementById(tab + '-status');
  el.textContent = msg;
  setTimeout(() => { el.textContent = ''; }, 3000);
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
}

showPage();
</script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/static/index.html
git commit -m "feat: add dashboard single-page UI"
```

---

## Task 8: `dashboard/Dockerfile` + container setup

**Files:**
- Create: `dashboard/Dockerfile`

- [ ] **Step 1: Create `dashboard/Dockerfile`**

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Test build locally**

```bash
docker build -t twitch-bot-dashboard ./dashboard
```
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add dashboard/Dockerfile
git commit -m "feat: add dashboard Dockerfile"
```

---

## Task 9: Docker Compose + GitHub Actions

**Files:**
- Modify: `docker-compose.yml`
- Create: `.github/workflows/dashboard.yml`

- [ ] **Step 1: Update `docker-compose.yml`**

Replace entire file with:

```yaml
services:
  twitch-bot:
    image: ghcr.io/jwsoat/twitch-bot:latest
    restart: unless-stopped
    volumes:
      - bot_data:/data
    environment:
      - TWITCH_TOKEN
      - TWITCH_BOT_NICK
      - HA_URL
      - HA_TOKEN
      - CHANNELS
      - ALLOWED_USERS
      - TTS_SERVICE
      - TTS_ENTITY
      - TTS_COOLDOWN_SEC
      - ENTITY_REFRESH_SEC
      - COMMAND_PREFIX
      - LOG_LEVEL
      - DB_PATH=/data/bot_data.db

  dashboard:
    image: ghcr.io/jwsoat/twitch-bot-dashboard:latest
    restart: unless-stopped
    volumes:
      - bot_data:/data
    ports:
      - "8080:8080"
    environment:
      - DB_PATH=/data/bot_data.db
      - DASHBOARD_USER
      - DASHBOARD_PASSWORD

  watchtower:
    image: containrrr/watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 300 twitch-bot dashboard

volumes:
  bot_data:
```

- [ ] **Step 2: Create `.github/workflows/dashboard.yml`**

```yaml
name: Build and push dashboard image

on:
  push:
    branches: [master]
    paths:
      - "dashboard/**"

jobs:
  build:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: ./dashboard
          push: true
          tags: ghcr.io/jwsoat/twitch-bot-dashboard:latest
```

- [ ] **Step 3: Commit and push**

```bash
git add docker-compose.yml .github/workflows/dashboard.yml
git commit -m "feat: add dashboard service to compose, dashboard CI workflow"
git push
```

- [ ] **Step 4: Wait for both GitHub Actions workflows to complete**

Check: https://github.com/jwsoat/twitch-bot/actions

Both `twitch-bot:latest` and `twitch-bot-dashboard:latest` must show green.

---

## Task 10: Integration + full test run

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```
.venv/Scripts/pytest -v
```
Expected: all tests pass (store, dashboard_db, dashboard_app, commands, entity_resolution, homeassistant, config, auth).

- [ ] **Step 2: Make `twitch-bot-dashboard` package public on GitHub**

Visit: https://github.com/jwsoat/twitch-bot/pkgs/container/twitch-bot-dashboard  
Package settings → Change visibility → Public

- [ ] **Step 3: Update Portainer stack**

In Portainer → Stacks → twitch-bot → Editor:
- Pull latest compose from git (or paste updated `docker-compose.yml`)
- Add env vars: `DASHBOARD_USER`, `DASHBOARD_PASSWORD`
- Update the stack

- [ ] **Step 4: Verify dashboard is accessible**

Visit `http://<proxmox-ip>:8080` → login page appears.
Login → Custom Commands tab loads → HA Commands tab shows all 10 built-in commands.

- [ ] **Step 5: Smoke test**

1. Add custom command `!test` → response "Hello from dashboard!" → Save
2. In Twitch chat: `!test` → bot replies "Hello from dashboard!"
3. Disable `!light` in HA Commands tab → in chat `!light lamp on` → no response
4. Re-enable `!light` → works again

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "feat: dashboard complete — custom commands + HA overrides"
git push
```
