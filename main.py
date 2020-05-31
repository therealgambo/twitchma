import asyncio
import logging
import re
import telnetlib3
import time

from confuse import Configuration
from logzero import logger
from twitchio.ext import commands
from twitchio.dataclasses import User, Message, NoticeSubscription

# Uncomment these two lines to enable crazy verbose debug logging
# logging.basicConfig(level=logging.DEBUG)


class TwitchMa(commands.Bot):

    def __init__(self, config: Configuration):
        super().__init__(
            irc_token=config['twitch']['auth_token'].get(),
            api_token=config['twitch']['auth_token'].get(),
            client_id=config['twitch']['client_id'].get(),
            nick=config['twitch']['username'].get(),
            prefix=config['bot']['command_prefix'].get(),
            initial_channels=[config['twitch']['username'].get()] + config['bot']['additional_channels'].get(),
        )
        self._config = config
        self._set_log_level()
        self._telnet = None
        self._telnet_connect()
        self._rate_limits = {}

    def _set_log_level(self):
        logger.setLevel(eval(f"logging.{self._config['twitch']['log_level'].get().upper()}"))

    def _check_user_access(self, user: User, required_access):
        required_access = required_access.lower()
        granted = False

        if user.name == self._config['twitch']['username'].get():
            granted = True
        if required_access == "all":
            granted = True
        if user.is_mod and (required_access == "mod" or required_access == "subscriber" or required_access == "turbo"):
            granted = True
        if user.is_turbo and required_access == "turbo":
            granted = True
        if user.is_subscriber and required_access == "subscriber":
            granted = True

        if granted:
            logger.debug(f"   - access granted: {user.name}")
            return True

        logger.debug(f"access denied for user '{user.name}' - does not have required access '{required_access}'")
        return False

    def _check_rate_limit(self, ctx, timeout=None, key=None):
        if ctx.author.name == self._config['twitch']['username'].get():
            return True

        if not timeout:
            timeout = self._config['bot']['command_timeout'].get()

        if ctx.command.name not in self._rate_limits.keys():
            self._rate_limits[ctx.command.name] = {}

        if ctx.author.name not in self._rate_limits[ctx.command.name].keys() and key is None:
            self._rate_limits[ctx.command.name][ctx.author.name] = -1
        elif ctx.author.name not in self._rate_limits[ctx.command.name].keys():
            self._rate_limits[ctx.command.name][ctx.author.name] = {}

        if ctx.author.name in self._rate_limits[ctx.command.name].keys() and \
                key is not None and \
                key not in self._rate_limits[ctx.command.name][ctx.author.name].keys():
            self._rate_limits[ctx.command.name][ctx.author.name][key] = -1

        if key in self._rate_limits[ctx.command.name][ctx.author.name].keys():
            last = self._rate_limits[ctx.command.name][ctx.author.name][key]
        else:
            last = self._rate_limits[ctx.command.name][ctx.author.name]

        now = time.time()
        if hasattr(time, 'monotonic'):
            now = time.monotonic()

        diff = (last + timeout) - now
        if diff < 0:
            if key is None:
                self._rate_limits[ctx.command.name][ctx.author.name] = now
            else:
                self._rate_limits[ctx.command.name][ctx.author.name][key] = now
            return True

        logger.debug(
            f"   - Rate limit reached. user: '{ctx.author.name}' "
            f"command: '{ctx.command.name}' key: '{key}' time remaining: '{diff}'"
        )
        return False

    """
    # TELNET SECTION
    ###########################################################################
    """

    def _telnet_connect(self):
        logger.debug("Connecting to GrandMA2...")
        self._telnet = telnetlib3.open_connection(
            self._config['grandma']['address'].get(),
            self._config['grandma']['port'].get(),
            shell=self._telnet_shell,
            log=logger
        )

        self._reader, self._writer = self.loop.run_until_complete(self._telnet)

    @asyncio.coroutine
    def _telnet_shell(self, reader, writer):
        while True:
            line = yield from reader.readline()
            line = line.rstrip()

            ansi_escape = re.compile(r"(\x9B|\x1B\[)[0-?]*[ -/]*[@-~]")
            line = ansi_escape.sub('', line)

            if re.match(r"^ \[.+]>Please login !", line):
                logger.debug("Authenticating with GrandMA2...")
                writer.write(
                    f"Login {self._config['grandma']['username'].get()} {self._config['grandma']['password'].get()}\r\n"
                )
            elif re.match(r"^Logged in as User '" + self._config['grandma']['username'].get().lower() + "'", line):
                logger.info("Connected to GrandMA2!")

    @asyncio.coroutine
    async def _telnet_send(self, command, ctx=None):
        if ctx is not None:
            logger.info(f"  - executing command for user '{ctx.message.author.name}': {command}")
        else:
            logger.info(f"  - executing command: {command}")
        self._writer.write(f"{command}\r\n")

    """
    # EVENTS SECTION
    ###########################################################################
    """

    async def event_ready(self):
        logger.info("Connected to Twitch!")

    async def event_join(self, user: User):
        command = self._config['commands']['twitch_events']['event_join']['command'].get()
        # ignore join events from ourself
        if command and not re.match(r"^" + self._config['twitch']['username'].get(), user.name):
            logger.debug(f"User joined: {user.name}, executing command: {command}")
            await self._telnet_send(command)

    async def event_part(self, user: User):
        command = self._config['commands']['twitch_events']['event_part']['command'].get()
        if command:
            logger.debug(f"User left: {user.name}, executing command: {command}")
            await self._telnet_send(command)

    async def event_message(self, message: Message):
        await self.handle_commands(message)

    async def event_command_error(self, ctx, error):
        logger.debug(f"User '{ctx.author.name}' entered a bad command: {ctx.message.content}")
        logger.debug(f"Exception message: {error}")
        command = self._config['commands']['twitch_events']['event_command_error']['command'].get()
        if command:
            await self._telnet_send(command)

    async def event_usernotice_subscription(self, subscription: NoticeSubscription):
        command = self._config['commands']['twitch_events']['event_usernotice_subscription']['command'].get()
        if command:
            logger.info(f"New Subscription! User '{subscription.user.name }', plan: {subscription.sub_plan_name}")
            await self._telnet_send(command)

    """
    # COMMANDS SECTION
    ###########################################################################
    """

    @commands.command(name='help')
    async def help_command(self, ctx):
        await ctx.send(f"Available commands: {', '.join(self.commands.keys())}")

    @commands.command(name='reloadconfig')
    async def reloadconfig_command(self, ctx):
        if self._check_user_access(ctx.author, ""):
            logger.debug("Reloading configuration...")
            cc = Configuration('twitch2ma', __name__)
            cc.set_file('./config.yaml')
            self._config = cc
            self._set_log_level()

    @commands.command(name='lb')
    async def lightbot_command(self, ctx):
        logger.debug(f"command: '{ctx.message.clean_content}'")
        args = ctx.message.clean_content[len(ctx.command.name):].lstrip(' ').split(' ')

        for arg in args:
            logger.debug(f"checking keyword: {arg}")

            index = [
                i for i, item in enumerate(self._config['commands']['keyword_mapping']['mappings']) if item['word'].get() == arg
            ]
            if len(index) == 0:
                logger.debug(f"  - Could not locate keyword '{arg}' in mapping")
                continue
            elif len(index) > 1:
                logger.error(
                    f"  - You have defined more than one mapping that uses the same keyword '{arg}'. Using first found."
                )

            mapping = self._config['commands']['keyword_mapping']['mappings'][index[0]].get()
            if self._check_user_access(ctx.message.author, mapping['access']) and \
                    self._check_rate_limit(ctx, mapping['timeout'], mapping['word']):
                await self._telnet_send(mapping['command'], ctx)

        logger.debug("######################################################")


if __name__ == "__main__":
    c = Configuration('twitch2ma', __name__)
    c.set_file('./config.yaml')
    TwitchMa(c).run()
