# Twitch → Home Assistant Bot — Design

**Date:** 2026-05-25
**Owner:** info@jwsoat.com

## Purpose

Twitch chat bot that lets four trusted users control a Home Assistant instance from chat: lights, scenes, media players, curtains (covers), and text-to-speech. Bot joins multiple Twitch channels simultaneously.

## Authorized users (allowlist)

Case-insensitive match against Twitch login name:

- `directorynetworks`
- `JwsoatMedia`
- `dylanwech`
- `directorynetwork`

Messages from anyone not in the allowlist are silently ignored (no reply, no log noise beyond debug-level).

## Channels joined

Configurable via `CHANNELS` env var. Default set:

- `directorynetworks`
- `JwsoatMedia`
- `dylanwech`
- `directorynetwork`

## Home Assistant connection

- Transport: HTTPS to Nabu Casa remote URL (e.g. `https://<id>.ui.nabu.casa`).
- Auth: Long-Lived Access Token in `Authorization: Bearer …` header.
- Library: `aiohttp` directly against HA REST API (`/api/states`, `/api/services/<domain>/<service>`). No third-party HA SDK needed — keeps deps small.

## Stack

- Python 3.11+
- `twitchio` — Twitch IRC client
- `aiohttp` — HA REST client
- `python-dotenv` — load `.env`
- `pytest` + `pytest-asyncio` — tests

## File layout

```
twitch bot/
├── bot.py              # entry; twitchio Bot subclass; command dispatch
├── homeassistant.py    # async HA client (call_service, get_states, EntityIndex)
├── auth.py             # allowlist check
├── commands.py         # command handler functions
├── config.py           # load + validate env vars
├── .env.example
├── requirements.txt
├── README.md
├── tests/
│   ├── test_auth.py
│   ├── test_homeassistant.py
│   ├── test_commands.py
│   └── test_entity_resolution.py
└── docs/superpowers/specs/2026-05-25-twitch-home-assistant-bot-design.md
```

## Components

### config.py
Reads env vars, fails fast with clear message on missing required values.

Required:
- `TWITCH_TOKEN` — oauth token for bot account (chat:read, chat:edit)
- `TWITCH_BOT_NICK` — bot's twitch username
- `HA_URL` — base URL (no trailing slash)
- `HA_TOKEN` — long-lived access token

Optional:
- `CHANNELS` — comma list, default `directorynetworks,JwsoatMedia,dylanwech,directorynetwork`
- `ALLOWED_USERS` — comma list, default the four above
- `TTS_SERVICE` — e.g. `tts.cloud_say` or `tts.google_translate_say`, default `tts.cloud_say`
- `TTS_ENTITY` — media_player entity_id to speak through (required only if TTS used)
- `TTS_COOLDOWN_SEC` — default `10`
- `ENTITY_REFRESH_SEC` — default `300`
- `COMMAND_PREFIX` — default `!`
- `LOG_LEVEL` — default `INFO`

### homeassistant.py

```
class HAClient:
    async def get_states() -> list[dict]
    async def call_service(domain: str, service: str, data: dict) -> None

class EntityIndex:
    # built from get_states(); rebuilt every ENTITY_REFRESH_SEC
    # structure: {domain: [(entity_id, friendly_name_lower, short_name_lower)]}
    def resolve(domain: str, query: str) -> ResolveResult
        # ResolveResult is one of: Match(entity_id), Ambiguous(list[entity_id]), NotFound
```

Resolution order (case-insensitive on the query):
1. exact match against `friendly_name` or short part of `entity_id` (after the dot)
2. prefix match
3. substring match
4. if multiple in any tier → Ambiguous returning up to 5 candidates

Refresh task runs in background; failures logged but do not crash bot (uses last known index).

### auth.py

```
def is_allowed(username: str, allowed: set[str]) -> bool
    # case-insensitive comparison; both sides lowercased
```

### commands.py

One async function per command. Each takes `(ctx, ha: HAClient, index: EntityIndex, args: list[str])` and is responsible for replying to chat on error or success. Reply format kept short to avoid Twitch's chat clutter.

Commands:

| Command | Args | HA action |
|---|---|---|
| `!light <name> on\|off` | name, state | `light.turn_on` / `light.turn_off`, `entity_id=<resolved>` |
| `!color <name> <color>` | name, color word | `light.turn_on`, `color_name=<color>` |
| `!bright <name> <0-100>` | name, pct | `light.turn_on`, `brightness_pct=<pct>` |
| `!scene <name>` | name | `scene.turn_on` |
| `!play <name>` | name | `media_player.media_play` |
| `!pause <name>` | name | `media_player.media_pause` |
| `!vol <name> <0-100>` | name, pct | `media_player.volume_set`, `volume_level=<pct/100>` |
| `!say <text>` | free text | `<TTS_SERVICE>`, `entity_id=<TTS_ENTITY>`, `message=<text>` |
| `!curtain <name> open\|close\|stop` | name, action | `cover.open_cover` / `close_cover` / `stop_cover` |
| `!entities <domain>` | domain | reply with first 10 friendly names known for that domain |

Numeric inputs are clamped to valid range. Unknown subcommands reply `usage: <signature>`.

### bot.py

Subclasses `twitchio.ext.commands.Bot`. On `event_ready`, kicks off entity index refresh task. On every command, runs:

```
1. is_allowed(ctx.author.name) → if no, return silently
2. dispatch to handler in commands.py
3. log structured line: ts | channel | user | cmd | args | result
```

## Logging

Standard Python `logging` to both stdout and rotating `bot.log` (1 MB × 5). Format:

```
2026-05-25T14:23:11Z INFO  channel=directorynetworks user=dylanwech cmd=!light args="lamp on" result=ok
```

Errors from HA include status code + short reason.

## Rate limiting

- `!say` per-channel cooldown of `TTS_COOLDOWN_SEC` (default 10s). Cooldown stored in memory.
- No global limit on other commands — allowlist is small and trusted.

## Error handling

- HA call raises → caught at command level → reply `HA error: <code>` (short, no token leak) → log full detail.
- Twitch disconnect → twitchio reconnect (built-in).
- Malformed user input → reply usage hint.
- Entity not found → reply `no <domain> matching "<query>"`.
- Ambiguous → reply `multiple: <a>, <b>, <c>`.

## Testing

`pytest` with `pytest-asyncio`.

- `test_auth.py` — case-insensitive allowlist, empty allowlist rejects all.
- `test_entity_resolution.py` — exact/prefix/substring tiers, ambiguity, not found, empty index.
- `test_homeassistant.py` — `aioresponses`-style mock for `get_states` and `call_service`; verifies URL, headers, body shape.
- `test_commands.py` — mocked HAClient + EntityIndex; verifies each command sends correct service call and replies with expected text on success/error.

Manual smoke test (documented in README): run bot against real HA, fire each command from an allowlisted account, confirm physical effect.

## Security

- All secrets in `.env`, never committed. `.gitignore` includes `.env`, `bot.log`.
- HA token transmitted only in `Authorization` header over HTTPS.
- Allowlist is the only authorization layer — explicitly documented in README.
- TTS cooldown limits damage if an allowlisted account is compromised.
- Bot does not echo HA tokens, URLs, or full error bodies into chat.

## Out of scope (deliberate)

- No web UI / dashboard.
- No multi-tier permissions (subs/VIPs/etc.).
- No persistent storage (no DB).
- No HA WebSocket subscriptions — REST polling for state is sufficient.
- No voice recognition / no Twitch alerts/EventSub.
- No alias config file — auto-discovery only.

## Success criteria

1. Bot starts, connects to all four channels, logs `ready`.
2. Allowlisted user in any joined channel runs `!light <real entity friendly name> on` and the physical light changes state within 3 seconds.
3. Non-allowlisted user running the same command sees no reply and the light does not change.
4. `!entities light` returns at least one real entity friendly name.
5. `!say hello world` produces audible speech from `TTS_ENTITY`.
6. All listed pytest tests pass.
