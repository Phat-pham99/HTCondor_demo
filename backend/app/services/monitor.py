"""Coordinates HTCondor queries, the event log, and output inspection into API models."""
from __future__ import annotations

import threading
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import Settings
from app.models import (
    ActivityItem,
    ClusterSummary,
    Job,
    JobCounts,
    JobDetail,
    JobEvents,
    JobFilter,
    JobList,
    JobOutput,
    JobState,
    Node,
    NodeCounts,
    NodeList,
    NodeState,
)
from app.services.condor_source import CondorSource
from app.services.events import EventStore
from app.services.lifecycle import build_job_detail, build_timeline, determine_failure, output_returned
from app.services.normalize import (
    ACTIVE_STATES,
    NodeRegistry,
    build_job,
    completed_counts,
    group_nodes,
    make_job_id,
    merge_job_ads,
    normalize_job_state,
)
from app.services.outputs import OutputInspector

FILTERS: dict[str, frozenset[JobState] | None] = {
    "all": None,
    "queued": frozenset({JobState.IDLE}),
    "running": frozenset({JobState.RUNNING, JobState.TRANSFERRING_OUTPUT}),
    "completed": frozenset({JobState.COMPLETED}),
    "failed": frozenset({JobState.FAILED, JobState.HELD}),
}


@dataclass(frozen=True)
class Snapshot:
    collected_at: datetime
    ads: dict[str, Mapping[str, Any]]
    jobs: dict[str, Job]
    nodes: list[Node]
    event_log_available: bool


class Monitor:
    def __init__(
        self,
        source: CondorSource,
        events: EventStore,
        outputs: OutputInspector,
        settings: Settings,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.source = source
        self.events = events
        self.outputs = outputs
        self.settings = settings
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshot: Snapshot | None = None
        self._taken = 0.0
        self._registry = NodeRegistry(settings.offline_retention_seconds)

    def _build_job(self, ad: Mapping[str, Any], origin: str, now: datetime) -> Job:
        state = normalize_job_state(ad)
        status = self.outputs.status(state, self.outputs.describe(ad))
        return build_job(ad, now=now, source=origin, output_status=status)

    def snapshot(self) -> Snapshot:
        with self._lock:
            now_ts = self._clock()
            if self._snapshot is not None and now_ts - self._taken < self.settings.cache_seconds:
                return self._snapshot
            pool = self.source.fetch(self.settings.history_limit)
            event_log_available = self.events.refresh()
            now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            ads: dict[str, Mapping[str, Any]] = {}
            jobs: dict[str, Job] = {}
            for (cluster_id, proc_id), (ad, origin) in merge_job_ads(pool.queue, pool.history).items():
                job_id = make_job_id(cluster_id, proc_id)
                ads[job_id] = ad
                jobs[job_id] = self._build_job(ad, origin, now)
            completed = completed_counts(jobs.values())
            nodes = self._registry.update(group_nodes(pool.startd, completed), completed, now)
            self._snapshot = Snapshot(now, ads, jobs, nodes, event_log_available)
            self._taken = now_ts
            return self._snapshot

    def _lookup(self, cluster_id: int, proc_id: int) -> tuple[Snapshot, Mapping[str, Any], Job] | None:
        snapshot = self.snapshot()
        job_id = make_job_id(cluster_id, proc_id)
        if job_id in snapshot.jobs:
            return snapshot, snapshot.ads[job_id], snapshot.jobs[job_id]
        # Older jobs may fall outside the cached history window.
        ad = self.source.find_job(cluster_id, proc_id)
        if ad is None:
            return None
        origin = "queue" if normalize_job_state(ad) in ACTIVE_STATES else "history"
        return snapshot, ad, self._build_job(ad, origin, snapshot.collected_at)

    def summary(self, activity_limit: int = 12) -> ClusterSummary:
        snapshot = self.snapshot()
        states = Counter(job.state for job in snapshot.jobs.values())
        nodes = Counter(node.state for node in snapshot.nodes)
        return ClusterSummary(
            collected_at=snapshot.collected_at,
            jobs=JobCounts(
                idle=states[JobState.IDLE],
                running=states[JobState.RUNNING],
                transferring_output=states[JobState.TRANSFERRING_OUTPUT],
                completed=states[JobState.COMPLETED],
                failed=states[JobState.FAILED],
                held=states[JobState.HELD],
                removed=states[JobState.REMOVED],
                unknown=states[JobState.UNKNOWN],
                total=len(snapshot.jobs),
            ),
            nodes=NodeCounts(
                total=len(snapshot.nodes) - nodes[NodeState.OFFLINE],
                busy=nodes[NodeState.CLAIMED],
                available=nodes[NodeState.AVAILABLE],
                unavailable=nodes[NodeState.UNAVAILABLE],
                offline=nodes[NodeState.OFFLINE],
            ),
            recent_activity=[
                ActivityItem(timestamp=event.timestamp, job_id=event.job_id, kind=event.kind,
                             title=event.title, host=event.host)
                for event in self.events.recent(activity_limit)
            ],
            event_log_available=snapshot.event_log_available,
            history_limit=self.settings.history_limit,
        )

    def jobs(self, job_filter: JobFilter = "all") -> JobList:
        snapshot = self.snapshot()
        allowed = FILTERS[job_filter]
        selected = [job for job in snapshot.jobs.values() if allowed is None or job.state in allowed]
        selected.sort(key=lambda job: (-job.cluster_id, job.proc_id))
        return JobList(collected_at=snapshot.collected_at, filter=job_filter, jobs=selected)

    def nodes(self) -> NodeList:
        snapshot = self.snapshot()
        return NodeList(collected_at=snapshot.collected_at, nodes=snapshot.nodes)

    def job_detail(self, cluster_id: int, proc_id: int) -> JobDetail | None:
        found = self._lookup(cluster_id, proc_id)
        if found is None:
            return None
        _, ad, job = found
        return build_job_detail(job, ad, build_timeline(ad, self.events.events_for(job.id)))

    def job_events(self, cluster_id: int, proc_id: int) -> JobEvents | None:
        found = self._lookup(cluster_id, proc_id)
        if found is None:
            return None
        snapshot, ad, job = found
        return JobEvents(
            job_id=job.id,
            event_log_available=snapshot.event_log_available,
            events=build_timeline(ad, self.events.events_for(job.id)),
        )

    def job_output(self, cluster_id: int, proc_id: int) -> JobOutput | None:
        found = self._lookup(cluster_id, proc_id)
        if found is None:
            return None
        _, ad, job = found
        timeline = build_timeline(ad, self.events.events_for(job.id))
        failure_stage, _ = determine_failure(job.state, ad, timeline)
        return JobOutput(
            job_id=job.id,
            status=job.output_status,
            returned=output_returned(job.state, job.output_status, timeline, failure_stage),
            files=self.outputs.describe(ad, include_preview=True),
        )
