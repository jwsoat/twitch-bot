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
