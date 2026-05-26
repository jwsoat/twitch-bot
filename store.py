from __future__ import annotations
import json
import logging
import os
import sqlite3
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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
    alias: str | None
    response_template: str | None
    enabled: bool
    allowed_users: list[str] | None  # None = use global allowlist


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
    except Exception as e:
        logger.warning("store read failed: %s", e)
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
        if users is not None and not isinstance(users, list):
            users = None
        return HAOverride(
            name=row[0], alias=row[1], response_template=row[2],
            enabled=bool(row[3]), allowed_users=users,
        )
    except Exception as e:
        # On DB error, return permissive defaults so the bot keeps running.
        # Commands fall back to global allowlist rather than silently blocking.
        logger.warning("store read failed: %s", e)
        return HAOverride(name=name, alias=None, response_template=None,
                          enabled=True, allowed_users=None)
