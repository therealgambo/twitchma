# TwitchMA

Twitch / GrandMA2 chat bot for the lolz - inspired from https://github.com/schw4rzlicht/twitch2ma

## Requirements

The following applications are required to run TwitchMA

- Python 3.7, or higher
- pip
- pipenv

## How to Run

Traditional way...

```
pipenv install && pipenv shell
python main.py
```

or for the ruthless cowboys...

```
pip install
python main.py
```

# Features

- Access Control
- Rate Limiting
- Default commands: !help, !lb, !reloadconfig

# TODO:
 
- Make commands configurable from `config.yaml` so those without programming experience can create new commands.
- Dockerfile

# Adding custom commands
Currently custom commands require you adding them to the `main.py` file under the `COMMANDS SECTION`.

Here are some examples:

```
    @commands.command(name='blah')
    async def blah_command(self, ctx):
        # this command has no rate-limit or access control applied
        await self._telnet_send('Go Macro 1337', ctx)
```
```
    @commands.command(name='blahblah')
    async def blah_command(self, ctx):
        # this command has no rate-limit but restricted with access control
        if self._check_user_access(ctx.message.author, 'subscriber'):
            await self._telnet_send('Go Macro 1337', ctx)
```
