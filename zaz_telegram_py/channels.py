import logging
import zmq
import json
from threading import Thread

# local
from .types import Project

def connect(sock, port):
    sock.connect(f"tcp://127.0.0.1:{port}")

class Req:
    def __init__(self, context, port):
        logging.info("Setting up requester on port %d", port)
        self.socket = context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.LINGER, 200)
        self.socket.setsockopt(zmq.RCVTIMEO, 1000)
        self.socket.setsockopt(zmq.SNDTIMEO, 100)
        connect(self.socket, port)

    def get(self, query):
        if isinstance(query, list):
            self.socket.send_multipart(query)
        else:
            self.socket.send_string(query)
        return json.loads(self.socket.recv_string())

    def _validate_response(self, json):
        if "error" in json:
            logging.error(f"Received error {json['error']}")
        return "error" not in json

    def _projects_from_json(self, json):
        projects = {}
        if self._validate_response(json):
            for p in json.keys():
                projects[p] = Project(**json[p])
        return projects

    def import_projects_by_ids(self, ids):
        b_ids = [id.encode('utf-8') for id in ids]
        result = self.get([b"projects", json.dumps(ids).encode('utf-8')])
        return self._projects_from_json(result)

    def import_projects(self):
        return self._projects_from_json(self.get("active-projects"))

    def import_current_phase(self, projects):
        logging.info("Getting current phase for %s", projects[0].id)
        logging.info("It's phases are %s", projects[0].phases)
        phase = self.get([b"project-current-phase", str(projects[0].id).encode('utf-8')])
        logging.info("=> %s", phase)

    def import_updates(self, since):
        self.get([b"updates-since", str(since).encode('utf-8')])

        
class Sub(Thread):
    def __init__(self, context, port, onmessage):
        Thread.__init__(self)
        self.port = port
        self.context = context
        self.onmessage = onmessage
        self.stopped = False

    def run(self):
        socket = self.context.socket(zmq.SUB)
        socket.setsockopt(zmq.SUBSCRIBE, b"")
        socket.setsockopt(zmq.LINGER, 200)
        socket.setsockopt(zmq.RCVTIMEO, 1000)
        connect(socket, self.port)

        while not self.stopped:
            try:
                data = socket.recv_multipart()
                if data:
                    logging.info(f"Received update {data}")
                    self.onmessage(data)
            except zmq.error.Again:
                pass

    def stop(self):
        self.stopped = True
