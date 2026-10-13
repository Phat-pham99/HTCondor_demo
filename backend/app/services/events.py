"""Incremental parser for the HTCondor job event log (text format)."""
from __future__ import annotations

import codecs
import os
import re
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

HEADER_RE = re.compile(
    r"^(?P<code>\d{3}) \((?P<cluster>-?\d+)\.(?P<proc>-?\d+)\.(?P<subproc>-?\d+)\) "
    r"(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?"
    r"|\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?)"
    r"\s*(?P<text>.*)$"
)
ALIAS_RE = re.compile(r"alias=([^&>\s]+)")
SINFUL_RE = re.compile(r"<([^:>\s]+)")
NORMAL_EXIT_RE = re.compile(r"Normal termination \(return value (-?\d+)\)")
SIGNAL_EXIT_RE = re.compile(r"Abnormal termination \(signal (\d+)\)")
HOLD_CODE_RE = re.compile(r"Code (\d+) Subcode (-?\d+)")

# Image-size, ad-information, attribute-update, and cluster/factory bookkeeping events.
SKIPPED_CODES = frozenset({6, 28, 33, 35, 36, 37, 38, 39})

EVENT_TYPES: dict[int, tuple[str, str]] = {
    0: ("SUBMITTED", "Submitted to the queue"),
    1: ("EXECUTION_STARTED", "Execution started"),
    2: ("EXECUTABLE_ERROR", "Executable error"),
    4: ("EVICTED", "Evicted from compute node"),
    5: ("TERMINATED", "Execution finished"),
    7: ("SHADOW_EXCEPTION", "Submit-side exception"),
    9: ("REMOVED", "Removed from the queue"),
    10: ("SUSPENDED", "Suspended"),
    11: ("UNSUSPENDED", "Resumed"),
    12: ("HELD", "Held"),
    13: ("RELEASED", "Released from hold"),
    21: ("REMOTE_ERROR", "Remote error"),
    22: ("DISCONNECTED", "Disconnected from compute node"),
    23: ("RECONNECTED", "Reconnected to compute node"),
    24: ("RECONNECT_FAILED", "Reconnection to compute node failed"),
    40: ("FILE_TRANSFER", "File transfer"),
}

TRANSFER_TITLES = {
    ("INPUT", "QUEUED"): "Input transfer queued",
    ("INPUT", "STARTED"): "Input transfer started",
    ("INPUT", "FINISHED"): "Input files delivered to compute node",
    ("OUTPUT", "QUEUED"): "Output transfer queued",
    ("OUTPUT", "STARTED"): "Output transfer started",
    ("OUTPUT", "FINISHED"): "Output returned to submit node",
}


@dataclass(frozen=True)
class ParsedEvent:
    cluster_id: int
    proc_id: int
    code: int
    timestamp: datetime
    kind: str
    title: str
    detail: str | None = None
    host: str | None = None
    exit_code: int | None = None
    signal: int | None = None
    hold_code: int | None = None

    @property
    def job_id(self) -> str:
        return f"{self.cluster_id}.{self.proc_id}"


def sinful_host(text: str) -> str | None:
    alias = ALIAS_RE.search(text)
    if alias:
        return alias.group(1)
    address = SINFUL_RE.search(text)
    return address.group(1) if address else None


def parse_timestamp(raw: str, tz: tzinfo, now: datetime | None = None) -> datetime:
    if "/" in raw[:5]:
        # Legacy "MM/DD HH:MM:SS" omits the year; assume the most recent matching date.
        current = (now or datetime.now(tz)).astimezone(tz)
        value = datetime.strptime(f"{current.year}/{raw.split('.')[0]}", "%Y/%m/%d %H:%M:%S")
        value = value.replace(tzinfo=tz)
        if value - current > timedelta(days=1):
            value = value.replace(year=value.year - 1)
        return value.astimezone(timezone.utc)
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    return value.astimezone(timezone.utc)


def _transfer_kind(text: str) -> tuple[str, str]:
    lowered = text.lower()
    direction = "INPUT" if "input" in lowered else "OUTPUT" if "output" in lowered else None
    if direction is None:
        return "FILE_TRANSFER", text or "File transfer"
    if "queue" in lowered:
        phase = "QUEUED"
    elif "started" in lowered:
        phase = "STARTED"
    elif "finished" in lowered:
        phase = "FINISHED"
    else:
        return f"{direction}_TRANSFER", text
    return f"{direction}_TRANSFER_{phase}", TRANSFER_TITLES[(direction, phase)]


def parse_block(lines: list[str], tz: tzinfo = timezone.utc, now: datetime | None = None) -> ParsedEvent | None:
    """Parse one event block. Returns None for ignored events; raises ValueError when malformed."""
    while lines and not lines[0].strip():
        lines = lines[1:]
    if not lines:
        raise ValueError("empty event block")
    match = HEADER_RE.match(lines[0].rstrip())
    if match is None:
        raise ValueError("unrecognized event header")
    code = int(match.group("code"))
    cluster_id = int(match.group("cluster"))
    proc_id = int(match.group("proc"))
    if code in SKIPPED_CODES or cluster_id < 0 or proc_id < 0:
        return None
    timestamp = parse_timestamp(match.group("ts"), tz, now)
    text = match.group("text").strip()
    body = [line.strip() for line in lines[1:] if line.strip()]
    kind, title = EVENT_TYPES.get(code, ("OTHER", text or f"Event {code:03d}"))
    detail: str | None = None
    host: str | None = None
    exit_code: int | None = None
    signal: int | None = None
    hold_code: int | None = None

    if code == 0:
        host = sinful_host(text)
    elif code == 1:
        slot = next((line.split(":", 1)[1].strip() for line in body if line.startswith("SlotName:")), None)
        host = slot or sinful_host(text)
    elif code == 5:
        joined = "\n".join(body)
        normal = NORMAL_EXIT_RE.search(joined)
        abnormal = SIGNAL_EXIT_RE.search(joined)
        if normal:
            exit_code = int(normal.group(1))
            title = "Execution completed" if exit_code == 0 else f"Execution failed (exit code {exit_code})"
        elif abnormal:
            signal = int(abnormal.group(1))
            title = f"Execution killed by signal {signal}"
    elif code == 12:
        hold = HOLD_CODE_RE.search("\n".join(body))
        hold_code = int(hold.group(1)) if hold else None
        reasons = [line for line in body if not HOLD_CODE_RE.match(line)]
        detail = reasons[0] if reasons else None
    elif code == 40:
        kind, title = _transfer_kind(text)
        host = next((sinful_host(line) for line in body if "host" in line.lower()), None)
    elif body:
        detail = body[0]

    return ParsedEvent(
        cluster_id=cluster_id,
        proc_id=proc_id,
        code=code,
        timestamp=timestamp,
        kind=kind,
        title=title,
        detail=detail,
        host=host,
        exit_code=exit_code,
        signal=signal,
        hold_code=hold_code,
    )


class EventLogParser:
    """Feeds text chunks and yields complete events; keeps partial blocks for the next chunk."""

    def __init__(self, tz: tzinfo = timezone.utc) -> None:
        self.tz = tz
        self.malformed = 0
        self._partial = ""
        self._block: list[str] = []

    def feed(self, text: str, now: datetime | None = None) -> list[ParsedEvent]:
        lines = (self._partial + text).split("\n")
        self._partial = lines.pop()
        events: list[ParsedEvent] = []
        for line in lines:
            line = line.rstrip("\r")
            if line.strip() != "...":
                self._block.append(line)
                continue
            block, self._block = self._block, []
            if not any(item.strip() for item in block):
                continue
            try:
                event = parse_block(block, self.tz, now)
            except ValueError:
                self.malformed += 1
                continue
            if event is not None:
                events.append(event)
        return events


def parse_event_log(text: str, tz: tzinfo = timezone.utc, now: datetime | None = None) -> list[ParsedEvent]:
    return EventLogParser(tz).feed(text, now)


class EventStore:
    """Tails the schedd's global event log and indexes events by job."""

    def __init__(self, path: Path, tz: tzinfo = timezone.utc, recent_limit: int = 100) -> None:
        self.path = Path(path)
        self.tz = tz
        self.recent_limit = recent_limit
        self.available = False
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self._parser = EventLogParser(self.tz)
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._offset = 0
        self._identity: tuple[int, int] | None = None
        self._by_job: dict[str, list[ParsedEvent]] = {}
        self._recent: deque[ParsedEvent] = deque(maxlen=self.recent_limit)

    @property
    def malformed(self) -> int:
        return self._parser.malformed

    def refresh(self) -> bool:
        with self._lock:
            try:
                stat = os.stat(self.path)
                identity = (stat.st_dev, stat.st_ino)
                if self._identity is not None and (identity != self._identity or stat.st_size < self._offset):
                    self._reset()
                self._identity = identity
                if stat.st_size > self._offset:
                    with open(self.path, "rb") as handle:
                        handle.seek(self._offset)
                        data = handle.read(stat.st_size - self._offset)
                    self._offset += len(data)
                    for event in self._parser.feed(self._decoder.decode(data)):
                        self._by_job.setdefault(event.job_id, []).append(event)
                        self._recent.append(event)
                self.available = True
            except OSError:
                self.available = False
            return self.available

    def events_for(self, job_id: str) -> list[ParsedEvent]:
        with self._lock:
            return list(self._by_job.get(job_id, ()))

    def recent(self, limit: int) -> list[ParsedEvent]:
        with self._lock:
            return list(self._recent)[-limit:][::-1]
