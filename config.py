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
    db_path: str


def load_config() -> Config:
    def req(key: str) -> str:
        val = os.getenv(key, "").strip()
        if not val:
            raise SystemExit(f"Missing required env var: {key}")
        return val

    def req_int(key: str, default: int) -> int:
        raw = os.getenv(key, str(default)).strip()
        try:
            return int(raw)
        except ValueError:
            raise SystemExit(f"Invalid integer for env var {key}: {raw!r}")

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
        tts_cooldown_sec=req_int("TTS_COOLDOWN_SEC", 10),
        entity_refresh_sec=req_int("ENTITY_REFRESH_SEC", 300),
        command_prefix=os.getenv("COMMAND_PREFIX", "!"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        db_path=os.getenv("DB_PATH", "/data/bot_data.db"),
    )
