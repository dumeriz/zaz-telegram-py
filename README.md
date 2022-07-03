# zaz-telegram-py

This is the code for the bot that serves the https://t.me/acceleratorz_updates channel. For the data backend, see https://github.com/dumerize/zenon-az.

## Usage
Place a configuration file `telegram.json` in `~/.config/zaz`. It must have the values for the fields `"token"`, `"chat"`, `"request"` and `"subscription"`. The first two configure the bot (its token and where to send its updates to), the last two are the ports of the service. I'm assuming localhost currently.

Install the bot using `pip install -e .`. This will only install a link, so changes to the code are automatically reflected after restarting. Start with:
```python
zaz-telegram-bot
```

## Status
Mostly operational. It has some minor bugs where the project and overview messages get out of sync. Also, the telegram api is giving me a lot of exceptions. Mostly regarding flooding protection, which is rather strict for bots in channels, but also http timeouts and other errors. I'm working around it a bit with an automatic rescheduler, that increases the delay for messages constantly until they have been delivered. But its an improvised fix and not always reliable. From time to time, I have to restart the bot to resync its internal state or resend messages from the backend manually, when I failed to catch an error from the telegram api. But it's usable. Fixes and improvements welcome.
