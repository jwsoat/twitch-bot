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
    monkeypatch.delenv("TTS_ENTITY", raising=False)
    cfg = load_config()
    assert "directorynetworks" in cfg.channels
    assert "jwsoatmedia" in cfg.allowed_users  # stored lowercase
    assert cfg.tts_entity is None
    assert cfg.tts_cooldown_sec == 10


def test_invalid_int_raises(monkeypatch):
    monkeypatch.setenv("TWITCH_TOKEN", "oauth:abc")
    monkeypatch.setenv("TWITCH_BOT_NICK", "mybot")
    monkeypatch.setenv("HA_URL", "https://example.ui.nabu.casa")
    monkeypatch.setenv("HA_TOKEN", "token123")
    monkeypatch.setenv("TTS_COOLDOWN_SEC", "notanumber")
    with pytest.raises(SystemExit):
        load_config()


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
