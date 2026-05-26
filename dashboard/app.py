from __future__ import annotations
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from pydantic import BaseModel

# Allow importing db from same directory
sys.path.insert(0, os.path.dirname(__file__))
import db as dashboard_db

DB_PATH = os.environ.get("DB_PATH", "/data/bot_data.db")
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "changeme")
_SECRET_KEY = DASHBOARD_PASSWORD + "_twitch_bot_jwt_v1"
_ALGORITHM = "HS256"
_TOKEN_EXPIRE_HOURS = 24

try:
    dashboard_db.init_db(DB_PATH)
except Exception:
    pass  # DB may not exist yet (e.g. during testing; fixture calls init_db on the patched path)

app = FastAPI(title="Twitch Bot Dashboard")
_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=_TOKEN_EXPIRE_HOURS)
    return jwt.encode({"sub": username, "exp": expire}, _SECRET_KEY, algorithm=_ALGORITHM)


def _current_user(token: Annotated[str, Depends(_oauth2)]) -> str:
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[_ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
        return username
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


class Token(BaseModel):
    access_token: str
    token_type: str


@app.post("/auth/token", response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user_ok = secrets.compare_digest(form_data.username, DASHBOARD_USER)
    pass_ok = secrets.compare_digest(form_data.password, DASHBOARD_PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return Token(access_token=_create_token(form_data.username), token_type="bearer")


# --- Custom commands ---

@app.get("/api/custom")
async def list_custom(_: Annotated[str, Depends(_current_user)]) -> list[dict]:
    return dashboard_db.list_custom_commands(DB_PATH)


class CustomCommandIn(BaseModel):
    name: str
    response: str
    cooldown_sec: int = 0
    restricted: bool = False
    enabled: bool = True


@app.post("/api/custom", status_code=201)
async def create_custom(
    cmd: CustomCommandIn,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.create_custom_command(DB_PATH, cmd.model_dump())
    return {"ok": True}


class CustomCommandUpdate(BaseModel):
    response: str
    cooldown_sec: int = 0
    restricted: bool = False
    enabled: bool = True


@app.put("/api/custom/{name}")
async def update_custom(
    name: str,
    cmd: CustomCommandUpdate,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.update_custom_command(DB_PATH, name, cmd.model_dump())
    return {"ok": True}


@app.delete("/api/custom/{name}")
async def delete_custom(
    name: str,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.delete_custom_command(DB_PATH, name)
    return {"ok": True}


# --- HA commands ---

@app.get("/api/ha")
async def list_ha(_: Annotated[str, Depends(_current_user)]) -> list[dict]:
    return dashboard_db.list_ha_commands(DB_PATH)


class HACommandUpdate(BaseModel):
    alias: str | None = None
    response_template: str | None = None
    enabled: bool = True
    allowed_users: list[str] = []


@app.put("/api/ha/{name}")
async def update_ha(
    name: str,
    cmd: HACommandUpdate,
    _: Annotated[str, Depends(_current_user)],
) -> dict:
    dashboard_db.update_ha_command(DB_PATH, name, cmd.model_dump())
    return {"ok": True}


# Serve static files last (catches all unmatched routes)
try:
    app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static"), html=True), name="static")
except Exception:
    pass  # static dir may not exist in test env
