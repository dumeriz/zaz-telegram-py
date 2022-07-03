import logging
import telegram
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CallbackContext, CommandHandler, TypeHandler, Defaults
from telegram.constants import ParseMode
import asyncio
import threading
import datetime
import time

chat_id = 0
application = None
job_timedelta_s = 2

# Working with a bot in a channel is a mess; it's constantly causing time outs.
# The job_queue interface has a 'when' parameter fortunately, so all jobs go through
# this naive scheduler
def schedule_job(job_executor, chat_id, context, add_delay=0):
    now = datetime.datetime.utcnow()
    try:
        delay = datetime.timedelta(seconds=job_timedelta_s + add_delay)
        schedule_job.when = max(now, schedule_job.when) + delay
    except AttributeError:
        schedule_job.when = now + datetime.timedelta(seconds=1)

    effective_delta = schedule_job.when - datetime.datetime.utcnow() 
    logging.debug(f"Scheduling job {context} to execute in {effective_delta}")
    application.job_queue.run_once(job_executor, schedule_job.when, chat_id=chat_id, context=context)

# Add a job to the scheduler with an increased timeout. This will still be followed by other
# scheduled messages that don't have that increased timeout, but maybe it's good enough.
def reschedule_job(job_executor, chat_id, context):
    if context.can_retry():
        logging.debug(f"Rescheduling job {context}; {context.exec_attempt + 1} attempt")
        schedule_job(job_executor, chat_id, context, add_delay=job_timedelta_s * context.exec_attempt)
    else:
        logging.error(f"Job {context} failed to execute")

def is_correct_chat(effective_chat_id):
    global chat_id
    return chat_id == effective_chat_id

class JobContext:
    def __init__(self):
        self.exec_attempt = 0
    
    def can_retry(self):
        self.exec_attempt += 1
        return self.exec_attempt < 5

class MessageSendContext(JobContext):
    def __init__(self, text, callback=None):
        JobContext.__init__(self)
        self.text = text
        self.callback = callback

    def __str__(self):
        return f"Send-Context for {self.text}"

class MessageEditContext(JobContext):
    def __init__(self, message_id, text):
        JobContext.__init__(self)
        self.message_id = message_id
        self.text = text

    def __str__(self):
        return f"Edit-{self.message_id}-Context for {self.text}"

class MessageDeleteContext(JobContext):
    def __init__(self, message_id):
        JobContext.__init__(self)
        self.message_id = message_id

    def __str__(self):
        return f"Delete-{self.message_id}-Context"

async def initiate_send(context: CallbackContext):
    text = context.job.context.text
    try:
        message = await context.bot.send_message(chat_id=context.job.chat_id, 
                                                 text=text)
        if context.job.context.callback:
            context.job.context.callback(message)
    except (telegram.error.TimedOut, telegram.error.RetryAfter) as e:
        logging.error(f"ERROR sending {text[0:20]}...: {str(e)}")
        reschedule_job(initiate_send, context.job.chat_id, context.job.context)
        #application.job_queue.run_once(initiate_send, 10, chat_id=context.job.chat_id, context=MessageSendContext(text, cb))
    except Exception as e:
        logging.error(str(e))

def send_message(msg: MessageSendContext, chat_id=None):
    if not chat_id:
        chat_id = globals()['chat_id']
    schedule_job(initiate_send, chat_id, msg)

async def initiate_edit(context: CallbackContext):
    m_id = context.job.context.message_id
    text = context.job.context.text
    try:
        await context.bot.editMessageText(chat_id=context.job.chat_id, 
                                          message_id=m_id, parse_mode=ParseMode.HTML,
                                          text=text)
    except telegram.error.BadRequest as bad:
        if bad.message.startswith("Message is not modified"):
            logging.debug("Ignoring edit error for unmodified message")
        else:
            logging.error(bad)
    except (telegram.error.TimedOut, telegram.error.RetryAfter) as e:
        logging.error(f"ERROR editing {m_id}: {str(e)}")
        reschedule_job(initiate_edit, context.job.chat_id, context.job.context)
        # application.job_queue.run_once(initiate_edit, 10, chat_id=context.job.chat_id, context=MessageEditContext(m_id, text))
    except Exception as e:
        logging.error(e)



def edit_message(edit: MessageEditContext, chat_id=None):
    if not chat_id:
        chat_id = globals()['chat_id']
    schedule_job(initiate_edit, chat_id, edit)

async def initiate_delete(context: CallbackContext):
    m_id = context.job.context.message_id
    try:
        await context.bot.delete_message(chat_id=context.job.chat_id, 
                                         message_id=m_id)
    except (telegram.error.TimedOut, telegram.error.RetryAfter) as e:
        logging.error(f"ERROR deleting {m_id}: {str(e)}")
        reschedule_job(initiate_delete, chat_id, context.job.context)
        # application.job_queue.run_once(initiate_delete, 10, chat_id=context.job.chat_id, context=MessageDeleteContext(m_id))
    except Exception as e:
        logging.error(str(e))

def delete_message(ctx: MessageDeleteContext, chat_id=None):
    if not chat_id:
        chat_id = globals()['chat_id']
    schedule_job(initiate_delete, chat_id, ctx)

def build_bot(token, group_chat_id):
    global chat_id
    global application
    chat_id = group_chat_id
    defaults = Defaults(parse_mode=ParseMode.HTML)
    application = ApplicationBuilder().token(token).defaults(defaults).build()
    
def run_bot():
    application.run_polling(write_timeout=10)
