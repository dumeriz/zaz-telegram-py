# zaz-telegram-py

This is the code for the bot that serves the https://t.me/acceleratorz_updates channel. For the data backend, see https://github.com/dumerize/zenon-az.

## Status
Mostly operational. It has some minor bugs where the project and overview messages get out of sync. Also, the telegram api is giving me a lot of exceptions. Mostly regarding flooding protection, which is rather strict for bots in channels, but also http timeouts and other errors. I'm working around it a bit with an automatic rescheduler, that increases the delay for messages constantly until they have been delivered. But its an improvised fix and not always reliable. From time to time, I have to restart the bot to resync its internal state or resend messages from the backend manually, when I failed to catch an error from the telegram api. But it's usable. Fixes and improvements welcome.
