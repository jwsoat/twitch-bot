import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant import EntityIndex, Match, NotFound, Ambiguous


def make_ctx(channel_name: str = "testchannel") -> MagicMock:
    ctx = MagicMock()
    ctx.send = AsyncMock()
    ctx.channel = MagicMock()
    ctx.channel.name = channel_name
    return ctx


def make_ha() -> AsyncMock:
    ha = AsyncMock()
    ha.call_service = AsyncMock()
    return ha


def make_index(domain: str, entity_id: str, friendly: str) -> EntityIndex:
    idx = EntityIndex()
    idx.build([{"entity_id": entity_id, "attributes": {"friendly_name": friendly}}])
    return idx


# --- light ---

async def test_light_on(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.living_room", "Living Room")
    await cmd_light(ctx, ha, idx, ["Living Room", "on"])
    ha.call_service.assert_called_once_with("light", "turn_on", {"entity_id": "light.living_room"})


async def test_light_off(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_light(ctx, ha, idx, ["lamp", "off"])
    ha.call_service.assert_called_once_with("light", "turn_off", {"entity_id": "light.lamp"})


async def test_light_bad_state(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_light(ctx, ha, idx, ["lamp", "toggle"])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]
    ha.call_service.assert_not_called()


async def test_light_not_found(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = EntityIndex()
    idx.build([])
    await cmd_light(ctx, ha, idx, ["unknown", "on"])
    ctx.send.assert_called_once()
    assert "no light" in ctx.send.call_args[0][0]


async def test_light_ambiguous(imports):
    from commands import cmd_light
    ctx = make_ctx()
    ha = make_ha()
    idx = EntityIndex()
    idx.build([
        {"entity_id": "light.a1", "attributes": {"friendly_name": "Lamp A"}},
        {"entity_id": "light.a2", "attributes": {"friendly_name": "Lamp B"}},
    ])
    await cmd_light(ctx, ha, idx, ["lamp", "on"])
    ctx.send.assert_called_once()
    assert "multiple" in ctx.send.call_args[0][0]


async def test_color(imports):
    from commands import cmd_color
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_color(ctx, ha, idx, ["lamp", "red"])
    ha.call_service.assert_called_once_with(
        "light", "turn_on", {"entity_id": "light.lamp", "color_name": "red"}
    )


async def test_bright_clamps(imports):
    from commands import cmd_bright
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_bright(ctx, ha, idx, ["lamp", "150"])
    ha.call_service.assert_called_once_with(
        "light", "turn_on", {"entity_id": "light.lamp", "brightness_pct": 100}
    )


async def test_bright_invalid_number(imports):
    from commands import cmd_bright
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("light", "light.lamp", "Lamp")
    await cmd_bright(ctx, ha, idx, ["lamp", "notanumber"])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]
