from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    value = int(raw)
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


@dataclass(frozen=True)
class Settings:
    collector_host: str = "condor-manager:9618"
    schedd_name: str = "condor-manager@condor-manager"
    event_log_path: Path = Path("/var/lib/condor/events/EventLog")
    output_root: Path = Path("/out")
    history_limit: int = 200
    cache_seconds: float = 2.0
    preview_bytes: int = 16384
    offline_retention_seconds: int = 3600

    @classmethod
    def from_environment(cls) -> "Settings":
        env = os.environ
        return cls(
            collector_host=env.get("DASHBOARD_COLLECTOR_HOST", cls.collector_host),
            schedd_name=env.get("DASHBOARD_SCHEDD_NAME", cls.schedd_name),
            event_log_path=Path(env.get("DASHBOARD_EVENT_LOG", str(cls.event_log_path))),
            output_root=Path(env.get("DASHBOARD_OUTPUT_ROOT", str(cls.output_root))),
            history_limit=_int("DASHBOARD_HISTORY_LIMIT", cls.history_limit, 1),
            cache_seconds=float(env.get("DASHBOARD_CACHE_SECONDS", cls.cache_seconds)),
            preview_bytes=_int("DASHBOARD_PREVIEW_BYTES", cls.preview_bytes, 1),
            offline_retention_seconds=_int(
                "DASHBOARD_OFFLINE_RETENTION_SECONDS", cls.offline_retention_seconds
            ),
        )
