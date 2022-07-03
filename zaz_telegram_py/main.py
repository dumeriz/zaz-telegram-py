# coding: utf-8
import logging
import signal
import time
import pprint
import random
import sys
import zmq
import json
import threading
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
from .channels import Req, Sub
from .types import (ProjectNew, ProjectVotesUpdate, ProjectStatusUpdate,
                    PhaseNew, PhaseUpdate, PhaseVotesUpdate, PhaseStatusUpdate,
                    PillarVotingStatus, ManualSend, funds)
from .bot import (build_bot, run_bot, send_message, edit_message, delete_message, 
                  MessageSendContext, MessageEditContext, MessageDeleteContext)
from .conf import TelegramState, TelegramConfig, telegram_log_file, init_paths

def log_uncaught_exception(exc_type, exc_value, exc_traceback):
    # don't log Ctrl-C
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logging.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

def setup_logging(config):
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(format=log_format, level=config.log_level())
    if config.log_to_stdout():
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logging.getLogger().addHandler(
            RotatingFileHandler(telegram_log_file(), maxBytes=50000, backupCount=5))
    sys.excepthook = log_uncaught_exception

stop = False

# interfaces with the bot module

def send_with_bot(text, callback=None):
    send_message(MessageSendContext(text, callback))

def edit_bot_message(message_id, text):
    edit_message(MessageEditContext(message_id, text))

def delete_bot_message(message_id):
    delete_message(MessageDeleteContext(message_id))

# zmq backend subscriber

class Subscriber():
    def __init__(self, context, port, onmessage):
        logging.info("Setting up subscriber on port %d", port)
        self.subscriber = Sub(context, port, onmessage)
        
    def __enter__(self):
        self.subscriber.start()
        return self.subscriber
    
    def __exit__(self, type, value, traceback):
        self.subscriber.stop()
        self.subscriber.join()
        logging.info("Subscriber joined")
        
# handler common funcs

def summary_phase_string(p):
    if p.status < 2:
        return ""
    else:
        return f"<i>{status_update_string(p.status)}</i>"

def summary_project_string(p):
    "Parameter p must be a project with status <= 1"
    if p.status == 1 and len(p.phases):
        phase_string = summary_phase_string(p.phases[-1])
        summary = f"<b>{p.name}</b> <i>Phase {len(p.phases)}</i>\n{p.phases[-1].votes}"
        return summary + phase_string
    elif p.status == 1:
        return f"<b>{p.name}</b>\n{p.votes} (<i>Accepted</i>)"
    elif p.status == 0:
        return f"<b>{p.name}</b>\n{p.votes}"
    else: # should not happen
        logging.error(f"Unexpected project status {p.status}")
        return ""

def format_overview_message(state):
    header = "<b>These projects need voting</b>\n\n"
    strings = state.get_project_strings()
    logging.info(f"Projectstrings: {strings}")
    return header + "\n".join(strings)

def status_update_string(value):
    strings = {1: "accepted", 2: "paid", 3: "closed", 4: "completed"}
    if value not in strings:
        logging.error(f"Invalid value {value} requested for status_update_string")
        return "<code>bot error</code>"
    return strings[value]

def handler(signum, frame):
    global stop
    stop = True

class Nop:
    def __init__(*args):
        pass

    def run(*args):
        pass

class HandlerContext:
    def __init__(self, zmq, config, state):
        self.zmq = zmq
        self.config = config
        self.state = state

class OverviewMessage:
    def __init__(self, context):
        self.ctx = context

    def _store_message_id(self, m):
        logging.info("Storing overview message id %d", m.message_id)
        self.ctx.state.set_message_id_overview(m.message_id)

    def _projects_that_need_action(self, projects):
        return sorted([p for p in projects.values() if project_needs_votes(p)], key=lambda p: p.created)

    def _make_and_store_project_text(self, project):
        text = summary_project_string(project)
        self.ctx.state.set_project_string(project.id, text)

    def _format_message(self, active_projects):
        [self._make_and_store_project_text(p) for p in active_projects]
        return format_overview_message(self.ctx.state)

    def run(self):
        "Creates a new overview message if none is configured yet. Else, updates the existing."
        active_projects = self.ctx.config.requester.import_projects()
        if active_projects:
            votable_projects = self._projects_that_need_action(active_projects)
            message_text = self._format_message(votable_projects)
            existing_message_id = self.ctx.state.message_id_overview()
            if 0 != existing_message_id:
                logging.info("Updating overview message with id=%d", existing_message_id)
                edit_bot_message(existing_message_id, message_text)
            else:
                logging.info("Creating new overview message")
                send_with_bot(message_text, lambda m: self._store_message_id(m))
            return active_projects

class ProjectsMessages:
    def __init__(self, context):
        self.ctx = context

    def _store_message_id_cb(self, project):
        return lambda m: self.ctx.state.project_message_id_store(project.id, m.message_id)
    
    def _delete_message(self, project_id):
        msg_id = self.ctx.state.project_message_id_remove(id)
        delete_bot_message(msg_id)

    def _update_existing(self, projects):
        for id in projects.keys():
            m_id = self.ctx.state.message_id_project(id)
            if m_id:
                logging.info("Editing {m_id}")
                edit_bot_message(m_id, str(projects[id]))
            else:
                logging.error("Can't find {m_id} for editing of {projects[id].name}")

    def run(self, active_projects, update_existing=False):
        [ids_new, ids_removed] = self.ctx.state.projects_diff(active_projects.keys())
        logging.info(f"Got {len(ids_new)} new and {len(ids_removed)} to delete")
        new_projects = sorted([active_projects[k] for k in active_projects if k in ids_new], key=lambda p: p.created)
        for p in new_projects:
            send_with_bot(str(p), callback=self._store_message_id_cb(p))

        # TODO: can't delete old project so have to retrieve the current state from the backend and
        #       update its message
        for id in ids_removed:
            self._delete_message(id)

        if update_existing:
            existing_ids = [k for k in active_projects if k not in ids_new and k not in ids_removed]
            self._update_existing({k: active_projects[k] for k in existing_ids})
            


class HandleRatesMessage:
    def __init__(self, context):
        self.ctx = context

    def _format_message(self, pillar_list):
        pillar_list.sort(key=lambda p: p.rate, reverse=True)
        strings = [f" <code>{p.active_rate:.2f}|{p.rate:.2f}</code> - {p.name}"
                   for p in pillar_list if p.rate > 0]
        header = "<b>Pillar participation rate (>0)</b>\n" + \
                 "for voting on active projects and phases\n" + \
                 "Ongoing | All time\n\n"
        never_voted = len(pillar_list) - len(strings)
        footer = f"{never_voted}/{len(pillar_list)} never voted"
        return header + "\n".join(strings) + "\n\n" + footer
    
    def run(self, pillar_rates):
        logging.info(f"New participation rates received for {len(pillar_rates)} pillars")
        message_text = self._format_message(pillar_rates)
        existing_message_id = self.ctx.state.message_id_rates()
        if 0 != existing_message_id:
            edit_bot_message(existing_message_id, message_text)
        else:
            send_with_bot(message_text, 
                          callback=lambda m: self.ctx.state.set_message_id_rates(m.message_id))

class HandleProjectRefresh:
    def __init__(self, context):
        self.ctx = context

    def _format_error(self, project_id, failed_thing):
        logging.error(f"Failed to get {failed_thing} during project refresh of {project_id}")

    def _refresh_project_message(self, project):
        message_id = self.ctx.state.message_id_project(project.id)
        if not message_id:
            self._format_error(project.id, "project-message")
            return False

        n = project.status
        edit_bot_message(message_id, str(project))
        if 1 < n:
            # Todo: does not work for older messages. Instead, replace the message text with a short notice?
            delete_bot_message(message_id)
            status = "paid" if n == 2 else "closed" if n == 3 else "completed"
            send_with_bot(f"<b>{project.name}</b>\nThe project has been {status}")
            self.ctx.state.project_message_id_remove(project.id)

        return True

    def _refresh_overview_message(self, project):
        OverviewMessage(self.ctx).run()
#        message_id = self.ctx.state.message_id_overview()
#        if not message_id:
#            self._format_error(project.id, "overview-message")
#            return False
#
#        if 0 < project.status and (project.status != 1 or not project.phases):
#            # Project is not open for voting, so remove from overview
#            self.ctx.state.del_project_string(project.id)
#        else:
#            self.ctx.state.set_project_string(project.id, summary_project_string(project))
#        edit_bot_message(message_id, format_overview_message(self.ctx.state))
        return True

    def run(self, project_id):
        result = self.ctx.config.requester.import_projects_by_ids([project_id])

        if not result:
            self._format_error(project_id, "project")
            return None

        project = result[project_id]
        self._refresh_overview_message(project) and self._refresh_project_message(project)
        return project
    
class HandleNewProject(HandleProjectRefresh):
    def __init__(self, context):
        HandleProjectRefresh.__init__(self, context)

    def _store_new_message_id(self, project, mid):
        logging.info(f"Storing new message id {mid} for project {project.name}")
        self.ctx.state.project_message_id_store(project.id, mid)

    def run(self, project):
        logging.info(f"RUN for HandleNewProject of {project}")
        HandleProjectRefresh._refresh_overview_message(self, project.data)
        send_with_bot(str(project), 
                callback=lambda m: self._store_new_message_id(project.data, m.message_id))
    
class HandleProjectUpdate(HandleProjectRefresh):
    def _init__(self, context):
        HandleProjectRefresh.__init__(self, context)

    def run(self, update):
        return HandleProjectRefresh.run(self, update.id)

class HandleProjectStatusUpdate(HandleProjectUpdate):
    def _init__(self, context):
        HandleProjectUpdate.__init__(self, context)

    def run(self, update):
        project = HandleProjectUpdate.run(self, update)
        if project:
            send_with_bot(f"<b>{project.name}</b>\nThe project has been {status_update_string(update.new)}")

def format_phase(phase):
    return f"<b>{phase.name}</b>\n{phase.description}\n{funds(phase)}\n\n{phase.url}"

#@dataclass
#class SyntheticProjectUpdate:
#    id: int

class HandleNewPhase(HandleProjectUpdate):
    def __init__(self, context):
        HandleProjectUpdate.__init__(self, context)

    def run(self, update):
        # Updates overview message and the project's message
        project = self.ctx.config.requester.import_projects_by_ids([update.data.pid])[update.data.pid]
        HandleProjectUpdate.run(self, project)
        #project = HandleProjectUpdate.run(self, SyntheticProjectUpdate(update.data.pid))
        send_with_bot(f"<b>{project.name}</b>\nNew phase is open for voting:\n\n{format_phase(update.data)}")

class HandlePhaseReset(HandleProjectUpdate):
    def __init__(self, context):
        HandleProjectUpdate.__init__(self, context)

    def run(self, update):
        # Updates overview message and the project's message
        project = self.ctx.config.requester.import_projects_by_ids([update.data.pid])[update.data.pid]
        HandleProjectUpdate.run(self, project)
        #project = HandleProjectUpdate.run(self, SyntheticProjectUpdate(update.data.pid))
        send_with_bot(f"<b>{project.name}</b>\nCurrent phase was reset:\n\n{format_phase(update.data)}")

class HandlePhaseUpdate(HandleProjectUpdate):
    def __init__(self, context):
        HandleProjectUpdate.__init__(self, context)

    def run(self, update):
        project = self.ctx.config.requester.import_projects_by_ids([update.pid])
        return HandleProjectUpdate.run(self, project[update.pid])
        #return HandleProjectUpdate.run(self, SyntheticProjectUpdate(update.pid))

class HandlePhaseStatusUpdate(HandlePhaseUpdate):
    def __init__(self, context):
        HandlePhaseUpdate.__init__(self, context)

    def run(self, update):
        project = HandlePhaseUpdate.run(self, update)
        if project:
            send_with_bot(f"<b>{project.name}</b>\nCurrent phase was {status_update_string(update.new)}")
            
class HandleManualUpdate:
    def __init__(self, context):
        self.context = context

    def run(self, update):
        text = update.text
        logging.info(f"Sending manual update {text}")
        send_with_bot(text)

# delegating updates received via zmq to corresponding handlers

def handle_update(update, zmq, config, state):

    # any key associated with a Nop value is not handled
    handler_map = {'project:new': [ProjectNew, HandleNewProject],
                   'project:votes-update': [ProjectVotesUpdate, HandleProjectUpdate],
                   'project:status-update': [ProjectStatusUpdate, HandleProjectStatusUpdate],
                   'phase:new': [PhaseNew, HandleNewPhase],
                   'phase:update': [PhaseUpdate, HandlePhaseReset],
                   'phase:votes-update': [PhaseVotesUpdate, HandlePhaseUpdate],
                   'phase:status-update': [PhaseStatusUpdate, HandlePhaseStatusUpdate],
                   'pillar-stats': [PillarVotingStatus, HandleRatesMessage],
                   'send': [ManualSend, HandleManualUpdate]}

    try:
        if len(update) == 1: # json style message
            js = json.loads(update[0])
            handler_key = js['type']
            del js['type']
        else: # multipart message
            handler_key = update[0].decode('utf-8')
            js = json.loads(update[1])
        h = handler_map[handler_key]
    except KeyError as ke:
        logging.error(f"No handler defined for {update}")
        h = [lambda x: None, Nop]

    ctor = h[0]
    handler = h[1](HandlerContext(zmq, config, state))
    try:
        typed_update = [ctor(**entry) for entry in js] if type(js) is list else ctor(**js)
    except Exception as e:
        logging.error(f"Failed to get typed update: {str(e)}")
        return

    logging.info(f"Running {handler_key}-handler")
    handler.run(typed_update)

def init_env():
    signal.signal(signal.SIGINT, handler)
    init_paths()
    config = TelegramConfig()
    setup_logging(config)
    logging.info("Logging to %s", telegram_log_file())
    logging.info("Found configuration in %s", config.filename)
    return config

def init_bot(config):
    logging.info("Starting bot for chat %d", config.chat())
    build_bot(config.token(), config.chat())
    state = TelegramState()
    logging.info("Telegram state loaded from %s, with %d projects", 
                 state.filename, len(state.message_ids_projects().keys()))
    return state

def project_is_active(p):
    return 1 == p.status

def current_phase_needs_votes(p):
    return len(p.phases) and 0 == p.phases[-1].status

def project_needs_votes(p):
    return 0 == p.status or project_is_active(p) and current_phase_needs_votes(p)

def do_after_bot_start(context, delay):
    time.sleep(delay)
    active_projects = OverviewMessage(context).run()
    #ProjectsMessages(ctx).run(active_projects, update_existing=True)

def main():
    config = init_env()
    state = init_bot(config)
    context = zmq.Context()
    
    config.requester = Req(context, config.request_port())

    with Subscriber(context, config.subscriber_port(), lambda s: handle_update(s, context, config, state)):
        global stop
        ctx = HandlerContext(context, config, state)
        # schedule update of the overview message after the bot started
        threading.Thread(target=do_after_bot_start, args=(ctx, 5))
        run_bot()
        stop = True
