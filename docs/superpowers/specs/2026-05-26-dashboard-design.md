# Dashboard Design Spec

## Goal

Web dashboard to manage Twitch bot commands — enable/disable, rename, edit responses, and add custom text commands — without editing code or redeploying.

## Architecture

Two Docker services share a SQLite file via a named Docker volume (`bot_data` mounted at `/data/` in both containers).

```
twitch-bot container          dashboard container
  store.py (reads SQLite)  ←→  dashboard/db.py (CRUD)
         └──────── /data/bot_data.db ────────┘
                   (Docker volume: bot_data)
```

Bot re-reads SQLite on every incoming command — no polling, no restart needed when config changes.

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS custom_commands (
    name        TEXT PRIMARY KEY,   -- command name without "!"
    response    TEXT NOT NULL,      -- static text response
    cooldown_sec INTEGER DEFAULT 0, -- 0 = no cooldown
    restricted  INTEGER DEFAULT 0,  -- 1 = allowed_users only, 0 = everyone
    enabled     INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ha_commands (
    name             TEXT PRIMARY KEY, -- built-in name: light, color, etc.
    alias            TEXT,             -- rename, NULL = use default
    response_template TEXT,            -- custom reply, NULL = use default
    enabled          INTEGER DEFAULT 1,
    allowed_users    TEXT              -- JSON array, NULL = use global allowlist
);
```

## New / Modified Files

### New files
- `store.py` — bot-side SQLite reads: `get_custom_commands()`, `get_ha_override(name)`
- `dashboard/Dockerfile` — Python 3.11-slim, installs dashboard/requirements.txt
- `dashboard/app.py` — FastAPI app: JWT auth, CRUD routes for both tables
- `dashboard/db.py` — SQLite CRUD (init schema, list/create/update/delete for each table)
- `dashboard/static/index.html` — single-page UI: login form + two-tab dashboard

### Modified files
- `commands.py` — `cmd_custom()` handler reads response from store; HA commands check `get_ha_override()` for enabled flag, alias, response, allowed_users
- `bot.py` — on `event_ready`, load custom commands from store and register them as twitchio commands; re-register when index refreshes
- `config.py` — add `db_path: str`, `dashboard_user: str`, `dashboard_password: str`, `dashboard_port: int` (default 8080)
- `docker-compose.yml` — add `dashboard` service + `bot_data` volume on both services

## Dashboard UI

Single HTML file, plain JS, no build step.

**Login page:** username + password → POST `/auth/token` → JWT stored in localStorage → redirect to dashboard.

**Tab 1 — Custom Commands:**
| Command | Response | Cooldown | Restricted | Enabled |
|---------|----------|----------|------------|---------|
| !discord | Join at discord.gg/... | 0s | No | ✅ |
- Add row button, inline edit, delete button per row
- Save on blur / explicit Save button

**Tab 2 — HA Commands:**
| Command | Alias | Response | Allowed Users | Enabled |
|---------|-------|----------|---------------|---------|
| light | | | | ✅ |
| color | | | | ✅ |
| ... | | | | |
- Pre-populated with all 10 built-in commands
- Blank alias = use default name
- Blank response = use default message
- Blank allowed users = use global allowlist from `.env`

## Authentication

- Single admin user: `DASHBOARD_USER` + `DASHBOARD_PASSWORD` env vars
- POST `/auth/token` returns JWT (HS256, 24h expiry)
- All other routes require `Authorization: Bearer <token>`
- Secret key derived from `DASHBOARD_PASSWORD` + a fixed salt

## API Routes

```
POST /auth/token                    → {access_token, token_type}

GET  /api/custom                    → list all custom commands
POST /api/custom                    → create custom command
PUT  /api/custom/{name}             → update custom command
DELETE /api/custom/{name}           → delete custom command

GET  /api/ha                        → list all HA command overrides
PUT  /api/ha/{name}                 → update HA command override
```

## Bot Behaviour Changes

**Custom commands:** On each Twitch message, bot checks if the command name matches any enabled row in `custom_commands`. If restricted=1, applies `is_allowed()` check. Respects cooldown_sec per channel using existing `TTSRateLimiter` pattern.

**HA command overrides:** Each existing HA command (light, color, etc.) calls `store.get_ha_override(name)` at the start of its handler. If `enabled=0`, silently returns. If `alias` set, bot registers command under alias name instead. If `allowed_users` set, uses that list instead of global allowlist. If `response_template` set, uses that for the reply message.

## Docker Compose Changes

```yaml
services:
  twitch-bot:
    image: ghcr.io/jwsoat/twitch-bot:latest
    restart: unless-stopped
    volumes:
      - bot_data:/data
    environment:
      - ... (existing vars)
      - DB_PATH=/data/bot_data.db

  dashboard:
    image: ghcr.io/jwsoat/twitch-bot-dashboard:latest
    restart: unless-stopped
    volumes:
      - bot_data:/data
    environment:
      - DB_PATH=/data/bot_data.db
      - DASHBOARD_USER
      - DASHBOARD_PASSWORD
      - DASHBOARD_PORT=8080
    ports:
      - "8080:8080"

  watchtower:
    image: containrrr/watchtower
    restart: unless-stopped
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 300 twitch-bot dashboard

volumes:
  bot_data:
```

## GitHub Actions

Second workflow `dashboard.yml` builds `ghcr.io/jwsoat/twitch-bot-dashboard:latest` from `dashboard/` on every push to master.

## Environment Variables Added

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_PATH` | No | `/data/bot_data.db` | SQLite file path |
| `DASHBOARD_USER` | Yes (dashboard) | — | Admin username |
| `DASHBOARD_PASSWORD` | Yes (dashboard) | — | Admin password |
| `DASHBOARD_PORT` | No | `8080` | Dashboard listen port |
