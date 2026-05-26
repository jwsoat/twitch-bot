import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def client(tmp_path):
    import dashboard.db as ddb
    db = str(tmp_path / "test.db")
    ddb.init_db(db)
    import dashboard.app as app_module
    # Patch module-level vars for this test
    app_module.DB_PATH = db
    app_module.DASHBOARD_USER = "admin"
    app_module.DASHBOARD_PASSWORD = "secret"
    app_module._SECRET_KEY = "secret_twitch_bot_jwt_v1"
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


def get_token(client):
    res = client.post("/auth/token", data={"username": "admin", "password": "secret"})
    return res.json()["access_token"]


def test_login_success(client):
    res = client.post("/auth/token", data={"username": "admin", "password": "secret"})
    assert res.status_code == 200
    assert "access_token" in res.json()


def test_login_wrong_password(client):
    res = client.post("/auth/token", data={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_list_custom_requires_auth(client):
    res = client.get("/api/custom")
    assert res.status_code == 401


def test_create_and_list_custom(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/custom", json={
        "name": "discord", "response": "discord.gg/xyz",
        "cooldown_sec": 0, "restricted": False, "enabled": True,
    }, headers=headers)
    res = client.get("/api/custom", headers=headers)
    assert res.status_code == 200
    assert res.json()[0]["name"] == "discord"


def test_delete_custom(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/custom", json={
        "name": "discord", "response": "x",
        "cooldown_sec": 0, "restricted": False, "enabled": True,
    }, headers=headers)
    client.delete("/api/custom/discord", headers=headers)
    res = client.get("/api/custom", headers=headers)
    assert res.json() == []


def test_list_ha_returns_all_builtins(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    res = client.get("/api/ha", headers=headers)
    names = {r["name"] for r in res.json()}
    assert "light" in names
    assert "curtain" in names


def test_update_ha_command(client):
    token = get_token(client)
    headers = {"Authorization": f"Bearer {token}"}
    client.put("/api/ha/light", json={
        "alias": "l", "response_template": "Lit!",
        "enabled": True, "allowed_users": [],
    }, headers=headers)
    res = client.get("/api/ha", headers=headers)
    light = next(r for r in res.json() if r["name"] == "light")
    assert light["alias"] == "l"
