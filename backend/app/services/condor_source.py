"""Read-only access to the HTCondor pool through the Python bindings."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

JOB_ATTRIBUTES = [
    "ClusterId", "ProcId", "GlobalJobId", "Owner", "JobStatus", "QDate", "JobStartDate",
    "JobCurrentStartDate", "JobCurrentStartExecutingDate", "LastMatchTime", "CompletionDate",
    "EnteredCurrentStatus", "RemoteHost", "LastRemoteHost", "RemoteWallClockTime", "ExitCode",
    "ExitBySignal", "ExitSignal", "HoldReason", "HoldReasonCode", "HoldReasonSubCode", "RemoveReason",
    "Cmd", "Args", "Arguments", "Iwd", "Out", "Err", "TransferOutput", "OutputDirectory",
    "TransferringInput", "TransferringOutput", "RequestCpus", "RequestMemory", "Requirements",
    "NumJobStarts", "NumShadowStarts",
]
NODE_ATTRIBUTES = [
    "Name", "Machine", "State", "Activity", "SlotType", "Cpus", "Memory", "TotalCpus", "TotalMemory",
    "JobId", "RemoteUser", "LastHeardFrom", "MyCurrentTime",
]
# Kept as source text rather than evaluated, because evaluation needs the matching machine ad.
EXPRESSION_ATTRIBUTES = frozenset({"Requirements"})
_CANONICAL = {name.lower(): name for name in JOB_ATTRIBUTES + NODE_ATTRIBUTES}


class SourceUnavailable(RuntimeError):
    """HTCondor could not be queried; distinct from a job failing."""


@dataclass
class PoolData:
    queue: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    startd: list[dict[str, Any]] = field(default_factory=list)


class CondorSource(Protocol):
    def fetch(self, history_limit: int) -> PoolData: ...

    def find_job(self, cluster_id: int, proc_id: int) -> dict[str, Any] | None: ...


def ad_to_dict(ad: Any, expression_type: type) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ad.keys():
        name = _CANONICAL.get(key.lower(), key)
        try:
            value = ad[key]
            if isinstance(value, expression_type):
                value = str(value) if name in EXPRESSION_ATTRIBUTES else ad.eval(key)
        except Exception:
            continue
        if isinstance(value, (bool, int, float, str)):
            result[name] = value
    return result


class HTCondorSource:
    def __init__(self, collector_host: str, schedd_name: str) -> None:
        self.collector_host = collector_host
        self.schedd_name = schedd_name

    @staticmethod
    def _bindings() -> tuple[Any, Any]:
        try:
            import classad2
            import htcondor2
        except ImportError as exc:
            raise SourceUnavailable("HTCondor Python bindings are not installed") from exc
        return htcondor2, classad2

    def _connect(self, htcondor2: Any) -> tuple[Any, Any]:
        collector = htcondor2.Collector(self.collector_host)
        schedd_ad = collector.locate(htcondor2.DaemonType.Schedd, self.schedd_name)
        return collector, htcondor2.Schedd(schedd_ad)

    def fetch(self, history_limit: int) -> PoolData:
        htcondor2, classad2 = self._bindings()
        try:
            collector, schedd = self._connect(htcondor2)
            queue = schedd.query(constraint="true", projection=JOB_ATTRIBUTES)
            history = schedd.history(constraint=None, projection=JOB_ATTRIBUTES, match=history_limit)
            startd = collector.query(htcondor2.AdType.Startd, projection=NODE_ATTRIBUTES)
        except Exception as exc:
            raise SourceUnavailable(f"HTCondor query failed: {exc}") from exc
        return PoolData(
            queue=[ad_to_dict(ad, classad2.ExprTree) for ad in queue],
            history=[ad_to_dict(ad, classad2.ExprTree) for ad in history],
            startd=[ad_to_dict(ad, classad2.ExprTree) for ad in startd],
        )

    def find_job(self, cluster_id: int, proc_id: int) -> dict[str, Any] | None:
        htcondor2, classad2 = self._bindings()
        constraint = f"ClusterId == {int(cluster_id)} && ProcId == {int(proc_id)}"
        try:
            _, schedd = self._connect(htcondor2)
            ads = schedd.query(constraint=constraint, projection=JOB_ATTRIBUTES, limit=1)
            if not ads:
                ads = schedd.history(constraint=constraint, projection=JOB_ATTRIBUTES, match=1)
        except Exception as exc:
            raise SourceUnavailable(f"HTCondor query failed: {exc}") from exc
        return ad_to_dict(ads[0], classad2.ExprTree) if ads else None
