# coding: utf-8
from appdirs import *
import os
import json
import logging

def appname():
    return "zaz"

def logdir():
    return user_log_dir(appname())

def datadir():
    return user_data_dir(appname())

def configdir():
    return user_config_dir(appname())

def assure_file_exists(f):
    with open(f, 'a+'): pass
    return f

def telegram_state_file():
    return os.path.join(datadir(), "telegram.json")

def telegram_config_file():
    return os.path.join(configdir(), "telegram.json")

def telegram_log_file():
    return os.path.join(logdir(), "telegram.log")

def init_paths():
    for dir in [datadir(), configdir(), logdir()]:
        print("creating ", dir)
        os.makedirs(dir, exist_ok=True)


class TelegramConfig:
    def __init__(self, filename=None):
        # can't use default to prevent evaluation before __init__
        self.filename = filename if filename else telegram_config_file()
        with open(self.filename, "r") as f:
            self.content = json.load(f)

    def token(self):
        return self.content["token"]

    def chat(self):
        return self.content["chat"]

    def request_port(self):
        return self.content["requests"]

    def subscriber_port(self):
        return self.content["subscriptions"]

    def log_to_stdout(self):
        try:
            return self.content["logstd"]
        except KeyError:
            return False

    def log_level(self):
        levels = {"info": logging.INFO, "debug": logging.DEBUG}
        try:
            return levels[self.content["loglevel"]]
        except KeyError:
            return levels["info"]

class TelegramState:
    default_content = {'message-ids': {'overview': 0, 'rates': 0, 'projects': {}}}

    def __init__(self, filename=None):
        # can't use default to prevent evaluation before __init__
        self.filename = filename if filename else telegram_state_file()
        if not os.path.exists(self.filename):
            self.content = TelegramState.default_content
            self.dump()
        
        with open(self.filename, "r") as f:
            self.content = json.load(f)

        self.project_strings = {}

    def dump(self):
        with open(self.filename, "w") as f:
            json.dump(self.content, f, indent=4)

    def get_project_strings(self):
        return self.project_strings.values() if self.project_strings else []

    def set_project_string(self, project_id, text):
        logging.info(f"Stored {project_id} in project_strings")
        self.project_strings[project_id] = text

    def del_project_string(self, project_id):
        try:
            del self.project_strings[project_id]
            logging.info(f"Deleted {project_id} from project_strings")
        except KeyError as ke:
            logging.warning(f"Tried to delete nonexisting key {project_id} from project_strings")

    def message_ids(self):
        return self.content['message-ids']

    def message_id_overview(self):
        return self.message_ids()['overview']

    def set_message_id_overview(self, id):
        self.message_ids()['overview'] = id
        self.dump()

    def message_id_rates(self):
        return self.message_ids()['rates']

    def set_message_id_rates(self, id):
        self.message_ids()['rates'] = id
        self.dump()

    def message_ids_projects(self):
        return self.message_ids()['projects']

    def message_id_project(self, project_id):
        try:
            return self.message_ids_projects()[project_id]
        except KeyError:
            return 0

    def projects_diff(self, project_ids):
        "Returns three lists of project ids: the first with new projects, the second with deleted projects, third with existing."
        new_projects = []
        deleted_projects = []

        for k in project_ids:
            if self.message_id_project(k) == 0:
                new_projects.append(k)

        for key in self.message_ids_projects():
            if not any(k for k in project_ids if k == key):
                deleted_projects.append(key)

        return new_projects, deleted_projects

    def project_message_id_store(self, project_id, message_id):
        logging.info(f"Storing {message_id} for {project_id}")
        self.message_ids_projects()[project_id] = message_id
        self.dump()

    def project_message_id_remove(self, project_id):
        logging.info(f"Removing {project_id} from registry")
        m_id = 0
        try:
            m_id = self.message_id_project(project_id)
            logging.info(f"Removing {m_id} for {project_id}")
            del self.message_ids_projects()[project_id]
            self.dump()
        except KeyError:
            logging.error(f"Attempt to delete message for nonexisting project-id {project_id}")
        return m_id

