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


def test_get_ha_override_malformed_allowed_users(db_path):
    with sqlite3.connect(db_path) as con:
        con.execute("INSERT INTO ha_commands VALUES ('light',NULL,NULL,1,'\"not-a-list\"')")
        con.commit()
    override = get_ha_override("light")
    assert override.allowed_users is None  # malformed JSON falls back to None
