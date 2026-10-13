from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class JobState(str, Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    TRANSFERRING_OUTPUT = "TRANSFERRING_OUTPUT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    HELD = "HELD"
    REMOVED = "REMOVED"
    UNKNOWN = "UNKNOWN"


class OutputStatus(str, Enum):
    PENDING = "PENDING"
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    NONE_DECLARED = "NONE_DECLARED"
    UNKNOWN = "UNKNOWN"


class NodeState(str, Enum):
    AVAILABLE = "AVAILABLE"
    CLAIMED = "CLAIMED"
    UNAVAILABLE = "UNAVAILABLE"
    OFFLINE = "OFFLINE"


class FailureStage(str, Enum):
    QUEUE = "QUEUE"
    INPUT_TRANSFER = "INPUT_TRANSFER"
    EXECUTION = "EXECUTION"
    OUTPUT_TRANSFER = "OUTPUT_TRANSFER"


class StepStatus(str, Enum):
    DONE = "DONE"
    CURRENT = "CURRENT"
    PENDING = "PENDING"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


JobFilter = Literal["all", "queued", "running", "completed", "failed"]


class Job(BaseModel):
    id: str
    cluster_id: int
    proc_id: int
    global_job_id: str | None = None
    owner: str | None = None
    state: JobState
    raw_status: str | None = None
    raw_status_code: int | None = None
    submitted_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    node: str | None = None
    slot: str | None = None
    queue_wait_seconds: int | None = None
    runtime_seconds: int | None = None
    exit_code: int | None = None
    output_status: OutputStatus
    command: str | None = None
    source: Literal["queue", "history"]


class LifecycleStep(BaseModel):
    key: str
    label: str
    status: StepStatus
    timestamp: datetime | None = None
    detail: str | None = None


class JobDetail(Job):
    arguments: str | None = None
    current_stage: str
    matched_at: datetime | None = None
    exit_by_signal: bool | None = None
    exit_signal: int | None = None
    hold_reason: str | None = None
    hold_reason_code: int | None = None
    failure_stage: FailureStage | None = None
    failure_reason: str | None = None
    output_returned: bool | None = None
    request_cpus: int | None = None
    request_memory_mb: int | None = None
    requirements: str | None = None
    job_starts: int | None = None
    lifecycle: list[LifecycleStep]
    raw: dict[str, Any]


class JobEvent(BaseModel):
    sequence: int
    timestamp: datetime
    code: int | None = None
    kind: str
    title: str
    detail: str | None = None
    host: str | None = None
    source: Literal["event_log", "job_ad"]


class JobEvents(BaseModel):
    job_id: str
    event_log_available: bool
    events: list[JobEvent]


class OutputFile(BaseModel):
    role: Literal["result", "stdout", "stderr"]
    name: str
    path: str
    exists: bool | None = None
    size_bytes: int | None = None
    modified_at: datetime | None = None
    preview: str | None = None
    truncated: bool = False
    note: str | None = None


class JobOutput(BaseModel):
    job_id: str
    status: OutputStatus
    returned: bool | None = None
    files: list[OutputFile]


class Slot(BaseModel):
    name: str
    state: str | None = None
    activity: str | None = None
    slot_type: str | None = None
    job_id: str | None = None
    cpus: int | None = None
    memory_mb: int | None = None


class Node(BaseModel):
    name: str
    state: NodeState
    raw_state: str | None = None
    slots: list[Slot]
    running_jobs: list[str]
    cpus_total: int | None = None
    cpus_allocated: int = 0
    memory_total_mb: int | None = None
    memory_allocated_mb: int = 0
    completed_jobs: int = 0
    last_update: datetime | None = None


class JobCounts(BaseModel):
    idle: int = 0
    running: int = 0
    transferring_output: int = 0
    completed: int = 0
    failed: int = 0
    held: int = 0
    removed: int = 0
    unknown: int = 0
    total: int = 0


class NodeCounts(BaseModel):
    total: int = 0
    busy: int = 0
    available: int = 0
    unavailable: int = 0
    offline: int = 0


class ActivityItem(BaseModel):
    timestamp: datetime
    job_id: str
    kind: str
    title: str
    host: str | None = None


class ClusterSummary(BaseModel):
    collected_at: datetime
    jobs: JobCounts
    nodes: NodeCounts
    recent_activity: list[ActivityItem]
    event_log_available: bool
    history_limit: int


class JobList(BaseModel):
    collected_at: datetime
    filter: JobFilter
    jobs: list[Job]


class NodeList(BaseModel):
    collected_at: datetime
    nodes: list[Node]
