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
