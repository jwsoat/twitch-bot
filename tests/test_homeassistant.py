import pytest
import aiohttp
from aioresponses import aioresponses
from ha_client import HAClient

BASE = "https://test.ui.nabu.casa"
TOKEN = "testtoken123"


@pytest.fixture
async def client():
    async with aiohttp.ClientSession() as session:
        yield HAClient(BASE, TOKEN, session)


async def test_get_states_returns_list(client):
    states = [{"entity_id": "light.test", "attributes": {"friendly_name": "Test"}}]
    with aioresponses() as m:
        m.get(f"{BASE}/api/states", payload=states)
        result = await client.get_states()
    assert result == states


async def test_get_states_sends_bearer_header(client):
    from yarl import URL
    with aioresponses() as m:
        m.get(f"{BASE}/api/states", payload=[])
        await client.get_states()
        key = ("GET", URL(f"{BASE}/api/states"))
        call = m.requests[key][0]
    assert call.kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"


async def test_call_service_posts_correct_url(client):
    from yarl import URL
    with aioresponses() as m:
        m.post(f"{BASE}/api/services/light/turn_on", payload={})
        await client.call_service("light", "turn_on", {"entity_id": "light.lamp"})
        key = ("POST", URL(f"{BASE}/api/services/light/turn_on"))
    assert key in m.requests


async def test_call_service_sends_json_body(client):
    from yarl import URL
    with aioresponses() as m:
        m.post(f"{BASE}/api/services/light/turn_on", payload={})
        await client.call_service("light", "turn_on", {"entity_id": "light.lamp"})
        key = ("POST", URL(f"{BASE}/api/services/light/turn_on"))
        call = m.requests[key][0]
    assert call.kwargs["json"] == {"entity_id": "light.lamp"}


async def test_call_service_raises_on_401(client):
    with aioresponses() as m:
        m.post(f"{BASE}/api/services/light/turn_on", status=401)
        with pytest.raises(aiohttp.ClientResponseError):
            await client.call_service("light", "turn_on", {})
