import asyncio

import aiohttp
import itsdangerous
import uvicorn

import breadcord

bot: breadcord.Bot
settings: breadcord.config.SettingsGroup
client: aiohttp.ClientSession
serializer: itsdangerous.URLSafeTimedSerializer


# patch uvicorn server to not eat signals w/o re-raising
class Server(uvicorn.Server):
    """A patched version of :class:`uvicorn.Server` that doesn't eat signals. See
    `<https://github.com/encode/uvicorn/issues/1579>`_ and `<https://github.com/encode/uvicorn/pull/1600>`.
    """

    # Override
    def install_signal_handlers(self) -> None:
        # Do nothing
        pass


class MyCog(breadcord.module.ModuleCog):
    def __init__(self):
        super().__init__("batter_control")

        global bot, settings
        bot = self.bot
        settings = self.settings

        self.website_task: asyncio.Task | None = None
        self.server: Server | None = None

    async def cog_load(self) -> None:
        # Generate a secret key if it isn't set
        if (secret_key := self.settings.get("secret_key")).value == "not set":
            import secrets
            secret_key.value = secrets.token_urlsafe(16)

        # Initialize the serializer for OAuth2 state parameter
        global serializer
        serializer = itsdangerous.URLSafeTimedSerializer(secret_key.value)

        # Initialize the aiohttp client session
        global client
        client = aiohttp.ClientSession()

        # Check to make sure client_id and client_secret are set
        if self.settings.get("client_id").value == "not set":
            self.logger.critical("`client_id\" not set! Refusing to start server.")
            return

        if self.settings.get("client_secret").value == "not set":
            self.logger.critical("`client_secret\" not set! Refusing to start server.")
            return

        # Start the web server
        host = self.settings.get("host").value
        port = self.settings.get("port").value
        config = uvicorn.Config(
            self.module.import_string + '.website:app',
            host=host,
            port=port,
            log_config=None,
        )
        self.server = Server(config)
        self.website_task = self.bot.loop.create_task(self.server.serve())

    async def cog_unload(self) -> None:
        if self.website_task is None:
            raise RuntimeError("Website task is None on cog_unload")

        if self.server is None:
            raise RuntimeError("Website server is None on cog_unload")

        await client.close()
        self.server.should_exit = True


async def setup(_bot):
    await _bot.add_cog(MyCog())
