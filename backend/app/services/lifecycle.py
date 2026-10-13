"""Build the ordered event timeline and lifecycle steps for one job."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.models import (
    FailureStage,
    Job,
    JobDetail,
    JobEvent,
    JobState,
    LifecycleStep,
    OutputStatus,
    StepStatus,
)
from app.services.events import ParsedEvent
from app.services.values import as_bool, as_datetime, as_int, as_str, split_slot

Ad = Mapping[str, Any]

# Breaks ties between events recorded in the same second; other events keep log order.
TIE_RANK = {"SUBMITTED": 0, "MATCHED": 1}

STEPS = (
    ("SUBMITTED", "Submitted"),
    ("QUEUED", "Waiting in queue"),
    ("MATCHED", "Matched with compute node"),
    ("RUNNING", "Running on compute node"),
    ("FINISHED", "Execution finished"),
    ("OUTPUT_RETURNED", "Output returned"),
)
STEP_INDEX = {key: index for index, (key, _) in enumerate(STEPS)}
FAILURE_STEP = {
    FailureStage.QUEUE: "QUEUED",
    FailureStage.INPUT_TRANSFER: "RUNNING",
    FailureStage.EXECUTION: "RUNNING",
    FailureStage.OUTPUT_TRANSFER: "OUTPUT_RETURNED",
}
TRANSFER_INPUT_HOLD_CODE = 13
TRANSFER_OUTPUT_HOLD_CODE = 12


def build_timeline(ad: Ad, parsed: list[ParsedEvent]) -> list[JobEvent]:
    entries = [
        JobEvent(
            sequence=0,
            timestamp=event.timestamp,
            code=event.code,
            kind=event.kind,
            title=event.title,
            detail=event.detail,
            host=event.host,
            source="event_log",
        )
        for event in parsed
    ]
    kinds = {event.kind for event in parsed}
    submitted = as_datetime(ad.get("QDate"))
    if "SUBMITTED" not in kinds and submitted is not None:
        entries.append(
            JobEvent(sequence=0, timestamp=submitted, kind="SUBMITTED", title="Submitted to the queue", source="job_ad")
        )
    matched = as_datetime(ad.get("LastMatchTime"))
    if matched is not None:
        slot, machine = split_slot(as_str(ad.get("RemoteHost")) or as_str(ad.get("LastRemoteHost")))
        entries.append(
            JobEvent(
                sequence=0,
                timestamp=matched,
                kind="MATCHED",
                title="Matched with a compute node",
                host=slot or machine,
                source="job_ad",
            )
        )
    entries.sort(key=lambda entry: (entry.timestamp, TIE_RANK.get(entry.kind, 2)))
    return [entry.model_copy(update={"sequence": index}) for index, entry in enumerate(entries, 1)]


def _has_started(ad: Ad, kinds: set[str]) -> bool:
    return (
        "EXECUTION_STARTED" in kinds
        or (as_int(ad.get("NumJobStarts")) or 0) > 0
        or as_datetime(ad.get("JobStartDate")) is not None
    )


def determine_failure(state: JobState, ad: Ad, timeline: list[JobEvent]) -> tuple[FailureStage | None, str | None]:
    kinds = {event.kind for event in timeline}
    if state == JobState.FAILED:
        if as_bool(ad.get("ExitBySignal")):
            signal = as_int(ad.get("ExitSignal"))
            return FailureStage.EXECUTION, f"Killed by signal {signal}" if signal is not None else "Killed by a signal"
        return FailureStage.EXECUTION, f"Exited with code {as_int(ad.get('ExitCode'))}"
    if state == JobState.HELD:
        reason = as_str(ad.get("HoldReason"))
        code = as_int(ad.get("HoldReasonCode"))
        if code == TRANSFER_INPUT_HOLD_CODE:
            return FailureStage.INPUT_TRANSFER, reason
        if code == TRANSFER_OUTPUT_HOLD_CODE:
            return FailureStage.OUTPUT_TRANSFER, reason
        return _stage_from_progress(ad, kinds), reason
    if state == JobState.REMOVED:
        return _stage_from_progress(ad, kinds), as_str(ad.get("RemoveReason")) or "Removed from the queue"
    return None, None


def _stage_from_progress(ad: Ad, kinds: set[str]) -> FailureStage:
    if not _has_started(ad, kinds):
        return FailureStage.QUEUE
    if "OUTPUT_TRANSFER_STARTED" in kinds and "OUTPUT_TRANSFER_FINISHED" not in kinds:
        return FailureStage.OUTPUT_TRANSFER
    return FailureStage.EXECUTION


def output_returned(state: JobState, output_status: OutputStatus, timeline: list[JobEvent],
                    failure_stage: FailureStage | None) -> bool | None:
    if any(event.kind == "OUTPUT_TRANSFER_FINISHED" for event in timeline) or output_status == OutputStatus.AVAILABLE:
        return True
    if failure_stage == FailureStage.OUTPUT_TRANSFER:
        return False
    if state in (JobState.COMPLETED, JobState.FAILED) and output_status in (OutputStatus.MISSING, OutputStatus.PARTIAL):
        return False
    return None


def describe_current_stage(job: Job, ad: Ad, failure_stage: FailureStage | None) -> str:
    node = job.node or "a compute node"
    if job.state == JobState.IDLE:
        return "Waiting in queue for a matching compute node"
    if job.state == JobState.RUNNING:
        if job.raw_status_code == 7:
            return f"Suspended on {node}"
        if as_bool(ad.get("TransferringInput")):
            return f"Transferring input files to {node}"
        return f"Running on {node}"
    if job.state == JobState.TRANSFERRING_OUTPUT:
        return f"Returning output from {node}"
    if job.state == JobState.COMPLETED:
        return "Completed successfully"
    if job.state == JobState.FAILED:
        return "Finished with an error"
    if job.state == JobState.HELD:
        return "Held by HTCondor" + (f" during {failure_stage.value.lower().replace('_', ' ')}" if failure_stage else "")
    if job.state == JobState.REMOVED:
        return "Removed from the queue"
    return "Unknown: HTCondor reported an unrecognized status"


def _last(timeline: list[JobEvent], kind: str) -> JobEvent | None:
    return next((event for event in reversed(timeline) if event.kind == kind), None)


def build_lifecycle(job: Job, timeline: list[JobEvent], failure_stage: FailureStage | None,
                    failure_reason: str | None, returned: bool | None) -> list[LifecycleStep]:
    submitted = next((event for event in timeline if event.kind == "SUBMITTED"), None)
    matched = _last(timeline, "MATCHED")
    executing = _last(timeline, "EXECUTION_STARTED")
    output_started = _last(timeline, "OUTPUT_TRANSFER_STARTED")
    output_finished = _last(timeline, "OUTPUT_TRANSFER_FINISHED")
    terminated = _last(timeline, "TERMINATED")
    submitted_at = submitted.timestamp if submitted else job.submitted_at

    timestamps = {
        "SUBMITTED": submitted_at,
        "QUEUED": submitted_at,
        "MATCHED": matched.timestamp if matched else None,
        "RUNNING": executing.timestamp if executing else job.started_at,
        "FINISHED": (output_started or terminated).timestamp if (output_started or terminated) else job.completed_at,
        "OUTPUT_RETURNED": output_finished.timestamp if output_finished else None,
    }
    node_detail = job.slot or job.node
    details: dict[str, str | None] = {"MATCHED": node_detail, "RUNNING": node_detail}

    state = job.state
    statuses: dict[str, StepStatus] = {}
    if state == JobState.IDLE:
        current, failed = "QUEUED", None
    elif state == JobState.RUNNING:
        current, failed = "RUNNING", None
    elif state == JobState.TRANSFERRING_OUTPUT:
        current, failed = "OUTPUT_RETURNED", None
    elif state in (JobState.COMPLETED, JobState.FAILED):
        current, failed = None, "FINISHED" if state == JobState.FAILED else None
    elif failure_stage is not None:
        current, failed = None, FAILURE_STEP[failure_stage]
    else:
        current, failed = "SUBMITTED", None

    pivot = current or failed
    pivot_index = STEP_INDEX[pivot] if pivot else len(STEPS)
    after = StepStatus.SKIPPED if state == JobState.REMOVED else StepStatus.PENDING
    for key, _ in STEPS:
        index = STEP_INDEX[key]
        if index < pivot_index:
            statuses[key] = StepStatus.DONE
        elif key == current:
            statuses[key] = StepStatus.CURRENT
        elif key == failed:
            statuses[key] = StepStatus.FAILED
        else:
            statuses[key] = after

    if state in (JobState.COMPLETED, JobState.FAILED):
        if returned is True:
            statuses["OUTPUT_RETURNED"] = StepStatus.DONE
        elif returned is False:
            statuses["OUTPUT_RETURNED"] = StepStatus.FAILED
        else:
            statuses["OUTPUT_RETURNED"] = StepStatus.SKIPPED
            details["OUTPUT_RETURNED"] = "No result files declared"
    if failed:
        details[failed] = failure_reason
    if state == JobState.COMPLETED and job.exit_code is not None:
        details["FINISHED"] = f"Exit code {job.exit_code}"
    if failure_stage == FailureStage.INPUT_TRANSFER:
        details["RUNNING"] = failure_reason or "Input transfer failed"

    return [
        LifecycleStep(key=key, label=label, status=statuses[key], timestamp=timestamps[key], detail=details.get(key))
        for key, label in STEPS
    ]


def build_job_detail(job: Job, ad: Ad, timeline: list[JobEvent]) -> JobDetail:
    failure_stage, failure_reason = determine_failure(job.state, ad, timeline)
    returned = output_returned(job.state, job.output_status, timeline, failure_stage)
    return JobDetail(
        **job.model_dump(),
        arguments=as_str(ad.get("Args")) or as_str(ad.get("Arguments")),
        current_stage=describe_current_stage(job, ad, failure_stage),
        matched_at=as_datetime(ad.get("LastMatchTime")),
        exit_by_signal=as_bool(ad.get("ExitBySignal")),
        exit_signal=as_int(ad.get("ExitSignal")),
        hold_reason=as_str(ad.get("HoldReason")),
        hold_reason_code=as_int(ad.get("HoldReasonCode")),
        failure_stage=failure_stage,
        failure_reason=failure_reason,
        output_returned=returned,
        request_cpus=as_int(ad.get("RequestCpus")),
        request_memory_mb=as_int(ad.get("RequestMemory")),
        requirements=as_str(ad.get("Requirements")),
        job_starts=as_int(ad.get("NumJobStarts")),
        lifecycle=build_lifecycle(job, timeline, failure_stage, failure_reason, returned),
        raw=dict(ad),
    )
