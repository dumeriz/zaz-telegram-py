from dataclasses import dataclass
from enum import Enum

class Status(Enum):
    PROJECT_NEEDS_VOTING = 0
    PROJECT_IS_ACCEPTED = 1
    PROJECT_IS_PAID = 2
    PROJECT_IS_CLOSED = 3
    PROJECT_IS_COMPLETED = 4
    PHASE_NEEDS_VOTING = 5
    PHASE_IS_ACTIVE = 6
    PHASE_IS_PAID = 7
    PHASE_IS_CLOSED = 8
    UNEXPECTED = 9

def get_status(project):
    if project.status in [0, 2, 3, 4]:
        return Status(project.status)
    if 0 == len(project.phases):
        return Status.PROJECT_IS_ACCEPTED
    phase = project.phases[-1]
    if 2 < phase.status:
        return Status.PHASE_IS_CLOSED
    else:
        # phase needs voting or is active or paid
        return Status(Status.PHASE_NEEDS_VOTING.value + phase.status)

@dataclass
class Votes:
    yes: int
    no: int
    abstain: int

    def __str__(self):
        return f"<b>Yes</b> {self.yes}, <b>No</b> {self.no}, <b>Abstain</b> {self.abstain}\n"

def funds(thing):
    return f"{thing.znn} ZNN, {thing.qsr} QSR"

def quorum_str():
    return f"<b>Quorum not reached yet</b>"

def status_string(project):
    value = get_status(project)
    if value is Status.PROJECT_NEEDS_VOTING:
        return str(project.votes) + f"\n{quorum_str()}"
    if value is Status.PROJECT_IS_ACCEPTED:
        return str(project.votes) + "\n<b>Accepted</b>"
    if value is Status.PROJECT_IS_CLOSED:
        return "<b>Closed</b>"
    if value is Status.PROJECT_IS_COMPLETED:
        return "<b>Completed</b>"
    n = len(project.phases)
    phase = project.phases[-1]
    if value is Status.PHASE_NEEDS_VOTING:
        return f"\nPhase {n}: {phase.name}\n{phase.url}\n{funds(phase)}\n" + str(phase.votes) + f"\n{quorum_str()}"
    status = "accepted" if value is Status.PHASE_IS_ACTIVE else f"paid {funds(phase)}" if value is Status.PHASE_IS_PAID else "closed"
    return f"\nPhase {n} has been {status}"

@dataclass
class PhaseData:
    id: str
    pid: str
    created: int
    name: str
    description: str
    url: str
    znn: int
    qsr: int
    status: int
    votes: Votes

    def __post_init__(self):
        self.votes = Votes(**self.votes)

@dataclass
class Project:
    id: str
    created: int
    description: str
    status: int
    name: str
    owner: str
    url: str
    qsr: int
    znn: int
    phases: list[PhaseData]
    votes: Votes

    def __post_init__(self):
        self.votes = Votes(**self.votes)
        self.phases = [PhaseData(**entry) for entry in self.phases]

    def __str__(self):
        return (f"<b>{self.name}</b>\n" + 
                f"Total: {funds(self)}\n" +
                status_string(self) + "\n\n" +
                f"{self.url}\n" +
                f"{self.description}\n\n")
                

@dataclass
class ProjectNew:
    id: str
    data: Project

    def __post_init__(self):
        self.data = Project(**self.data)

    def __str__(self):
        return (f"<b>New proposal</b>\n"
                f"{self.data}")

@dataclass
class ProjectStatusUpdate:
    id: str
    old: int
    new: int

@dataclass
class ProjectVotesUpdate:
    id: str
    data: Votes

    def __post_init__(self):
        self.data = Votes(**self.data)

@dataclass
class PhaseNew:
    id: str
    data: PhaseData

    def __post_init__(self):
        self.data = PhaseData(**self.data)

@dataclass
class PhaseUpdate:
    id: str
    old: str
    data: PhaseData

    def __post_init__(self):
        self.data = PhaseData(**self.data)

@dataclass
class PhaseStatusUpdate:
    id: str
    pid: str
    old: int
    new: int

@dataclass
class PhaseVotesUpdate:
    id: str
    pid: str
    data: Votes

    def __post_init__(self):
        self.data = Votes(**self.data)

@dataclass
class PillarVotingStatus:
    name: str
    rate: float
    active_rate: float

@dataclass
class ManualSend:
    text: str
