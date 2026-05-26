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
