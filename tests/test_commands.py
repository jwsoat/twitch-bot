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


# --- scene ---

async def test_scene(imports):
    from commands import cmd_scene
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("scene", "scene.party_mode", "Party Mode")
    await cmd_scene(ctx, ha, idx, ["party"])
    ha.call_service.assert_called_once_with(
        "scene", "turn_on", {"entity_id": "scene.party_mode"}
    )


async def test_scene_no_args(imports):
    from commands import cmd_scene
    ctx = make_ctx()
    ha = make_ha()
    idx = EntityIndex()
    idx.build([])
    await cmd_scene(ctx, ha, idx, [])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]


# --- media ---

async def test_play(imports):
    from commands import cmd_play
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_play(ctx, ha, idx, ["tv"])
    ha.call_service.assert_called_once_with(
        "media_player", "media_play", {"entity_id": "media_player.tv"}
    )


async def test_pause(imports):
    from commands import cmd_pause
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_pause(ctx, ha, idx, ["tv"])
    ha.call_service.assert_called_once_with(
        "media_player", "media_pause", {"entity_id": "media_player.tv"}
    )


async def test_vol_sets_fractional(imports):
    from commands import cmd_vol
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_vol(ctx, ha, idx, ["tv", "50"])
    ha.call_service.assert_called_once_with(
        "media_player", "volume_set", {"entity_id": "media_player.tv", "volume_level": 0.5}
    )


async def test_vol_clamps_to_100(imports):
    from commands import cmd_vol
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("media_player", "media_player.tv", "TV")
    await cmd_vol(ctx, ha, idx, ["tv", "200"])
    ha.call_service.assert_called_once_with(
        "media_player", "volume_set", {"entity_id": "media_player.tv", "volume_level": 1.0}
    )


# --- curtain ---

async def test_curtain_open(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "open"])
    ha.call_service.assert_called_once_with(
        "cover", "open_cover", {"entity_id": "cover.blinds"}
    )


async def test_curtain_close(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "close"])
    ha.call_service.assert_called_once_with(
        "cover", "close_cover", {"entity_id": "cover.blinds"}
    )


async def test_curtain_stop(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "stop"])
    ha.call_service.assert_called_once_with(
        "cover", "stop_cover", {"entity_id": "cover.blinds"}
    )


async def test_curtain_bad_action(imports):
    from commands import cmd_curtain
    ctx = make_ctx()
    ha = make_ha()
    idx = make_index("cover", "cover.blinds", "Blinds")
    await cmd_curtain(ctx, ha, idx, ["blinds", "flip"])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]


# --- say ---

async def test_say_calls_tts(imports):
    from commands import cmd_say, TTSRateLimiter
    ctx = make_ctx()
    ha = make_ha()
    limiter = TTSRateLimiter(cooldown_sec=0)
    await cmd_say(ctx, ha, "tts.cloud_say", "media_player.speaker", limiter, "ch", ["hello", "world"])
    ha.call_service.assert_called_once_with(
        "tts", "cloud_say",
        {"entity_id": "media_player.speaker", "message": "hello world"}
    )


async def test_say_no_tts_entity(imports):
    from commands import cmd_say, TTSRateLimiter
    ctx = make_ctx()
    ha = make_ha()
    limiter = TTSRateLimiter(cooldown_sec=0)
    await cmd_say(ctx, ha, "tts.cloud_say", None, limiter, "ch", ["hello"])
    ctx.send.assert_called_once_with("TTS not configured")
    ha.call_service.assert_not_called()


async def test_say_cooldown_blocks(imports):
    from commands import cmd_say, TTSRateLimiter
    ctx = make_ctx()
    ha = make_ha()
    limiter = TTSRateLimiter(cooldown_sec=9999)
    # First call passes
    await cmd_say(ctx, ha, "tts.cloud_say", "media_player.speaker", limiter, "ch", ["hello"])
    # Second call blocked
    ctx2 = make_ctx()
    ha2 = make_ha()
    await cmd_say(ctx2, ha2, "tts.cloud_say", "media_player.speaker", limiter, "ch", ["hello"])
    ctx2.send.assert_called_once_with("TTS cooldown active")
    ha2.call_service.assert_not_called()


# --- entities ---

async def test_entities_lists_domain(imports):
    from commands import cmd_entities
    ctx = make_ctx()
    idx = EntityIndex()
    idx.build([
        {"entity_id": "light.lamp", "attributes": {"friendly_name": "Lamp"}},
    ])
    await cmd_entities(ctx, idx, ["light"])
    ctx.send.assert_called_once()
    assert "light.lamp" in ctx.send.call_args[0][0]


async def test_entities_no_args(imports):
    from commands import cmd_entities
    ctx = make_ctx()
    idx = EntityIndex()
    idx.build([])
    await cmd_entities(ctx, idx, [])
    ctx.send.assert_called_once()
    assert "usage" in ctx.send.call_args[0][0]
