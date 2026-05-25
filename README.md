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
python -m venv .venv
# Windows:
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python bot.py
# macOS/Linux:
.venv/bin/pip install -r requirements.txt
.venv/bin/python bot.py
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

Entity `<name>` is matched by friendly name or entity_id suffix (fuzzy, case-insensitive). Use `!entities <domain>` to discover what names are available.

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
