"""Translate raw job and slot ClassAds into the dashboard's stable model."""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any

from app.models import Job, JobState, Node, NodeState, OutputStatus, Slot
from app.services.values import as_bool, as_datetime, as_int, as_str, seconds_between, split_slot

Ad = Mapping[str, Any]

RAW_STATUS_NAMES = {
    1: "Idle",
    2: "Running",
    3: "Removed",
    4: "Completed",
    5: "Held",
    6: "Transferring Output",
    7: "Suspended",
}
EXECUTING_STATES = frozenset({JobState.RUNNING, JobState.TRANSFERRING_OUTPUT})
ACTIVE_STATES = EXECUTING_STATES | {JobState.IDLE}
FINISHED_STATES = frozenset({JobState.COMPLETED, JobState.FAILED})
CLAIMED_SLOT_STATES = frozenset({"Claimed", "Matched", "Preempting"})
AVAILABLE_SLOT_STATES = frozenset({"Unclaimed"})


def make_job_id(cluster_id: int, proc_id: int) -> str:
    return f"{cluster_id}.{proc_id}"


def job_key(ad: Ad) -> tuple[int, int] | None:
    cluster_id = as_int(ad.get("ClusterId"))
    proc_id = as_int(ad.get("ProcId"))
    if cluster_id is None or proc_id is None or cluster_id < 0 or proc_id < 0:
        return None
    return cluster_id, proc_id


def exited_unsuccessfully(ad: Ad) -> bool:
    if as_bool(ad.get("ExitBySignal")):
        return True
    exit_code = as_int(ad.get("ExitCode"))
    return exit_code is not None and exit_code != 0


def normalize_job_state(ad: Ad) -> JobState:
    code = as_int(ad.get("JobStatus"))
    if code == 1:
        return JobState.IDLE
    if code in (2, 7):
        return JobState.RUNNING
    if code == 3:
        return JobState.REMOVED
    if code == 4:
        return JobState.FAILED if exited_unsuccessfully(ad) else JobState.COMPLETED
    if code == 5:
        return JobState.HELD
    if code == 6:
        return JobState.TRANSFERRING_OUTPUT
    return JobState.UNKNOWN


def merge_job_ads(
    queue_ads: Iterable[Ad], history_ads: Iterable[Ad]
) -> dict[tuple[int, int], tuple[Ad, str]]:
    """Combine queue and history, keeping the most recent ad per job (history wins ties)."""
    merged: dict[tuple[int, int], tuple[Ad, str]] = {}
    for origin, ads in (("queue", queue_ads), ("history", history_ads)):
        for ad in ads:
            key = job_key(ad)
            if key is None:
                continue
            current = merged.get(key)
            if current is None or _entered(ad) >= _entered(current[0]):
                merged[key] = (ad, origin)
    return merged


def _entered(ad: Ad) -> int:
    return as_int(ad.get("EnteredCurrentStatus")) or 0


def job_node(ad: Ad, state: JobState) -> tuple[str | None, str | None]:
    if state == JobState.IDLE:
        return None, None
    return split_slot(as_str(ad.get("RemoteHost")) or as_str(ad.get("LastRemoteHost")))


def build_job(ad: Ad, *, now: datetime, source: str, output_status: OutputStatus) -> Job:
    key = job_key(ad)
    if key is None:
        raise ValueError("job ad has no valid ClusterId/ProcId")
    cluster_id, proc_id = key
    state = normalize_job_state(ad)
    status_code = as_int(ad.get("JobStatus"))
    slot, machine = job_node(ad, state)

    submitted = as_datetime(ad.get("QDate"))
    first_start = as_datetime(ad.get("JobStartDate")) or as_datetime(ad.get("JobCurrentStartDate"))
    current_start = as_datetime(ad.get("JobCurrentStartDate")) or first_start
    completed = as_datetime(ad.get("CompletionDate"))

    if first_start is not None:
        queue_wait = seconds_between(submitted, first_start)
    elif state == JobState.IDLE:
        queue_wait = seconds_between(submitted, now)
    else:
        queue_wait = None

    if state in EXECUTING_STATES:
        runtime = seconds_between(current_start, now)
    elif completed is not None and current_start is not None:
        runtime = seconds_between(current_start, completed)
    else:
        wall_clock = as_int(ad.get("RemoteWallClockTime"))
        runtime = wall_clock if wall_clock and wall_clock > 0 else None

    return Job(
        id=make_job_id(cluster_id, proc_id),
        cluster_id=cluster_id,
        proc_id=proc_id,
        global_job_id=as_str(ad.get("GlobalJobId")),
        owner=as_str(ad.get("Owner")),
        state=state,
        raw_status=RAW_STATUS_NAMES.get(status_code) if status_code is not None else None,
        raw_status_code=status_code,
        submitted_at=submitted,
        started_at=None if state == JobState.IDLE else current_start,
        completed_at=completed,
        node=machine,
        slot=slot,
        queue_wait_seconds=queue_wait,
        runtime_seconds=runtime,
        exit_code=as_int(ad.get("ExitCode")) if state in FINISHED_STATES else None,
        output_status=output_status,
        command=as_str(ad.get("Cmd")),
        source="history" if source == "history" else "queue",
    )


def build_slot(ad: Ad) -> Slot:
    name = as_str(ad.get("Name")) or as_str(ad.get("Machine")) or "unknown"
    return Slot(
        name=name,
        state=as_str(ad.get("State")),
        activity=as_str(ad.get("Activity")),
        slot_type=as_str(ad.get("SlotType")),
        job_id=as_str(ad.get("JobId")),
        cpus=as_int(ad.get("Cpus")),
        memory_mb=as_int(ad.get("Memory")),
    )


def node_state(slots: Iterable[Slot]) -> NodeState:
    states = {slot.state for slot in slots}
    if states & CLAIMED_SLOT_STATES:
        return NodeState.CLAIMED
    if states & AVAILABLE_SLOT_STATES:
        return NodeState.AVAILABLE
    return NodeState.UNAVAILABLE


def _max_int(values: Iterable[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return max(present) if present else None


def _node_from_slots(machine: str, ads: list[Ad], completed_jobs: int) -> Node:
    slots = sorted((build_slot(ad) for ad in ads), key=lambda slot: slot.name)
    allocated = [
        slot
        for slot in slots
        if slot.state in CLAIMED_SLOT_STATES and slot.slot_type != "Partitionable"
    ]
    cpus_total = _max_int(as_int(ad.get("TotalCpus")) for ad in ads)
    if cpus_total is None:
        cpus_total = sum(slot.cpus or 0 for slot in slots) or None
    memory_total = _max_int(as_int(ad.get("TotalMemory")) for ad in ads)
    if memory_total is None:
        memory_total = sum(slot.memory_mb or 0 for slot in slots) or None
    updates = [
        as_datetime(ad.get("LastHeardFrom")) or as_datetime(ad.get("MyCurrentTime")) for ad in ads
    ]
    raw_states = sorted({f"{slot.state or '?'}/{slot.activity or '?'}" for slot in slots})
    return Node(
        name=machine,
        state=node_state(slots),
        raw_state=", ".join(raw_states) or None,
        slots=slots,
        running_jobs=sorted({slot.job_id for slot in slots if slot.job_id and slot.state == "Claimed"}),
        cpus_total=cpus_total,
        cpus_allocated=sum(slot.cpus or 0 for slot in allocated),
        memory_total_mb=memory_total,
        memory_allocated_mb=sum(slot.memory_mb or 0 for slot in allocated),
        completed_jobs=completed_jobs,
        last_update=max((update for update in updates if update), default=None),
    )


def group_nodes(startd_ads: Iterable[Ad], completed: Mapping[str, int]) -> dict[str, Node]:
    by_machine: dict[str, list[Ad]] = {}
    for ad in startd_ads:
        machine = as_str(ad.get("Machine")) or split_slot(ad.get("Name"))[1]
        if machine:
            by_machine.setdefault(machine, []).append(ad)
    return {
        machine: _node_from_slots(machine, ads, completed.get(machine, 0))
        for machine, ads in by_machine.items()
    }


def completed_counts(jobs: Iterable[Job]) -> Counter[str]:
    return Counter(job.node for job in jobs if job.node and job.raw_status_code == 4)


class NodeRegistry:
    """Remembers nodes that stopped advertising so they can be shown as OFFLINE."""

    def __init__(self, retention_seconds: int) -> None:
        self.retention_seconds = retention_seconds
        self._seen: dict[str, tuple[Node, datetime]] = {}

    def update(
        self, current: Mapping[str, Node], completed: Mapping[str, int], now: datetime
    ) -> list[Node]:
        for name, node in current.items():
            self._seen[name] = (node, now)
        result: dict[str, Node] = dict(current)
        for name, (node, seen_at) in list(self._seen.items()):
            if name in current:
                continue
            if (now - seen_at).total_seconds() > self.retention_seconds:
                del self._seen[name]
                continue
            result[name] = _offline(name, completed.get(name, 0), node, seen_at)
        for name, count in completed.items():
            if name not in result:
                result[name] = _offline(name, count, None, None)
        return sorted(result.values(), key=lambda node: (node.state == NodeState.OFFLINE, node.name))


def _offline(name: str, completed: int, last: Node | None, seen_at: datetime | None) -> Node:
    return Node(
        name=name,
        state=NodeState.OFFLINE,
        slots=[],
        running_jobs=[],
        cpus_total=last.cpus_total if last else None,
        memory_total_mb=last.memory_total_mb if last else None,
        completed_jobs=completed,
        last_update=(last.last_update if last and last.last_update else seen_at),
    )
