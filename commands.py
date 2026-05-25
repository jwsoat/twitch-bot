from __future__ import annotations
import logging
import time
from typing import Any, Protocol

from homeassistant import HAClient, EntityIndex, Match, Ambiguous, NotFound

logger = logging.getLogger(__name__)


class ChatContext(Protocol):
    async def send(self, message: str) -> None: ...
    channel: Any


async def _resolve(
    ctx: ChatContext, index: EntityIndex, domain: str, name: str
) -> str | None:
    result = index.resolve(domain, name)
    if isinstance(result, Match):
        return result.entity_id
    if isinstance(result, Ambiguous):
        await ctx.send(f"multiple {domain}s: {', '.join(result.candidates)}")
        return None
    await ctx.send(f'no {domain} matching "{name}"')
    return None


async def cmd_light(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2 or args[1].lower() not in ("on", "off"):
        await ctx.send("usage: !light <name> on|off")
        return
    name, state = args[0], args[1].lower()
    entity_id = await _resolve(ctx, index, "light", name)
    if not entity_id:
        return
    service = "turn_on" if state == "on" else "turn_off"
    try:
        await ha.call_service("light", service, {"entity_id": entity_id})
        await ctx.send(f"light {entity_id} {state}")
    except Exception as e:
        logger.error("light error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_color(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2:
        await ctx.send("usage: !color <name> <color>")
        return
    name, color = args[0], args[1].lower()
    entity_id = await _resolve(ctx, index, "light", name)
    if not entity_id:
        return
    try:
        await ha.call_service(
            "light", "turn_on", {"entity_id": entity_id, "color_name": color}
        )
        await ctx.send(f"light {entity_id} color → {color}")
    except Exception as e:
        logger.error("color error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")


async def cmd_bright(
    ctx: ChatContext, ha: HAClient, index: EntityIndex, args: list[str]
) -> None:
    if len(args) < 2:
        await ctx.send("usage: !bright <name> <0-100>")
        return
    name = args[0]
    try:
        pct = max(0, min(100, int(args[1])))
    except ValueError:
        await ctx.send("usage: !bright <name> <0-100>")
        return
    entity_id = await _resolve(ctx, index, "light", name)
    if not entity_id:
        return
    try:
        await ha.call_service(
            "light", "turn_on", {"entity_id": entity_id, "brightness_pct": pct}
        )
        await ctx.send(f"light {entity_id} brightness → {pct}%")
    except Exception as e:
        logger.error("bright error: %s", e)
        await ctx.send(f"HA error: {getattr(e, 'status', 'unknown')}")
