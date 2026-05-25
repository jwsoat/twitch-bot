from __future__ import annotations
import asyncio
import logging
import logging.handlers
import sys

import aiohttp
from twitchio.ext import commands

import commands as cmd_module
from auth import is_allowed
from commands import TTSRateLimiter
from config import Config, load_config
from ha_client import EntityIndex, HAClient

logger = logging.getLogger("bot")


def setup_logging(level: str) -> None:
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    root = logging.getLogger()
    root.setLevel(level)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)
    fh = logging.handlers.RotatingFileHandler(
        "bot.log", maxBytes=1_000_000, backupCount=5
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


class TwitchBot(commands.Bot):
    def __init__(
        self, cfg: Config, ha: HAClient, index: EntityIndex
    ) -> None:
        super().__init__(
            token=cfg.twitch_token,
            prefix=cfg.command_prefix,
            initial_channels=cfg.channels,
        )
        self._cfg = cfg
        self._ha = ha
        self._index = index
        self._limiter = TTSRateLimiter(cfg.tts_cooldown_sec)

    async def event_ready(self) -> None:
        logger.info(
            "ready nick=%s channels=%s", self.nick, self._cfg.channels
        )
        await self._refresh_index()
        asyncio.create_task(self._refresh_loop())

    async def _refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self._cfg.entity_refresh_sec)
            await self._refresh_index()

    async def _refresh_index(self) -> None:
        try:
            states = await self._ha.get_states()
            self._index.build(states)
            total = self._index.count()
            logger.info("entity index refreshed count=%d", total)
        except Exception as e:
            logger.error("entity refresh failed: %s", e)

    def _gate(self, ctx: commands.Context) -> bool:
        if not is_allowed(ctx.author.name, self._cfg.allowed_users):
            logger.debug(
                "blocked user=%s channel=%s",
                ctx.author.name,
                ctx.channel.name,
            )
            return False
        return True

    def _log(self, ctx: commands.Context) -> None:
        logger.info(
            "channel=%s user=%s cmd=%s",
            ctx.channel.name,
            ctx.author.name,
            ctx.message.content.split()[0],
        )

    @commands.command(name="light")
    async def light(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_light(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="color")
    async def color(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_color(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="bright")
    async def bright(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_bright(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="scene")
    async def scene(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_scene(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="play")
    async def play(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_play(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="pause")
    async def pause(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_pause(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="vol")
    async def vol(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_vol(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="curtain")
    async def curtain(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_curtain(ctx, self._ha, self._index, list(args))
        self._log(ctx)

    @commands.command(name="say")
    async def say(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_say(
            ctx,
            self._ha,
            self._cfg.tts_service,
            self._cfg.tts_entity,
            self._limiter,
            ctx.channel.name,
            list(args),
        )
        self._log(ctx)

    @commands.command(name="entities")
    async def entities(self, ctx: commands.Context, *args: str) -> None:
        if not self._gate(ctx):
            return
        await cmd_module.cmd_entities(ctx, self._index, list(args))
        self._log(ctx)


async def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)
    async with aiohttp.ClientSession() as session:
        ha = HAClient(cfg.ha_url, cfg.ha_token, session)
        index = EntityIndex()
        bot = TwitchBot(cfg, ha, index)
        await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
