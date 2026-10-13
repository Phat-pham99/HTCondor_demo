import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.services.events import EventStore, parse_event_log
from app.services.lifecycle import build_timeline
from fixtures import BASE, FAILED_LOG, SUCCESS_LOG, job_ad


class ParseTests(unittest.TestCase):
    def test_parses_successful_lifecycle_in_order(self):
        events = parse_event_log(SUCCESS_LOG)
        self.assertEqual(
            [event.kind for event in events],
            [
                "SUBMITTED",
                "INPUT_TRANSFER_STARTED",
                "INPUT_TRANSFER_FINISHED",
                "EXECUTION_STARTED",
                "OUTPUT_TRANSFER_STARTED",
                "OUTPUT_TRANSFER_FINISHED",
                "TERMINATED",
            ],
        )
        self.assertEqual(events[0].timestamp, datetime(2026, 10, 13, 10, 20, 15, tzinfo=timezone.utc))
        self.assertEqual(events[0].host, "condor-manager")
        self.assertEqual(events[1].host, "condor-worker-1-0")
        self.assertEqual(events[3].host, "slot1@condor-worker-1-0")
        self.assertEqual(events[-1].exit_code, 0)
        self.assertEqual(events[-1].title, "Execution completed")

    def test_parses_failure_and_hold(self):
        events = parse_event_log(FAILED_LOG)
        terminated = events[2]
        self.assertEqual((terminated.job_id, terminated.exit_code), ("13.0", 1))
        self.assertIn("exit code 1", terminated.title)
        held = events[3]
        self.assertEqual((held.job_id, held.kind, held.hold_code), ("14.0", "HELD", 12))
        self.assertTrue(held.detail.startswith("Transfer output files failure"))

    def test_legacy_timestamp_uses_recent_year(self):
        text = "000 (001.000.000) 12/31 23:59:00 Job submitted from host: <10.0.0.1:1>\n...\n"
        now = datetime(2027, 1, 1, 0, 5, tzinfo=timezone.utc)
        [event] = parse_event_log(text, now=now)
        self.assertEqual(event.timestamp, datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc))

    def test_timestamp_with_offset_is_converted_to_utc(self):
        text = "000 (001.000.000) 2026-10-13T12:00:00+02:00 Job submitted from host: <10.0.0.1:1>\n...\n"
        [event] = parse_event_log(text)
        self.assertEqual(event.timestamp, datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc))

    def test_malformed_blocks_are_skipped(self):
        text = "garbage line\n...\n" + SUCCESS_LOG.split("...\n", 1)[0] + "...\n"
        events = parse_event_log(text)
        self.assertEqual([event.kind for event in events], ["SUBMITTED"])


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "EventLog"

    def tearDown(self):
        self.directory.cleanup()

    def test_missing_file_is_reported_unavailable(self):
        store = EventStore(self.path)
        self.assertFalse(store.refresh())
        self.assertEqual(store.events_for("12.0"), [])

    def test_reads_incrementally_and_waits_for_complete_blocks(self):
        head, tail = SUCCESS_LOG[:120], SUCCESS_LOG[120:]
        self.path.write_text(head)
        store = EventStore(self.path)
        self.assertTrue(store.refresh())
        self.assertEqual(store.events_for("12.0"), [])
        with self.path.open("a") as handle:
            handle.write(tail)
        store.refresh()
        self.assertEqual(len(store.events_for("12.0")), 7)
        self.assertEqual(store.recent(1)[0].kind, "TERMINATED")

    def test_truncated_log_is_reread_from_start(self):
        self.path.write_text(SUCCESS_LOG)
        store = EventStore(self.path)
        store.refresh()
        self.path.write_text(FAILED_LOG)
        store.refresh()
        self.assertEqual(store.events_for("12.0"), [])
        self.assertEqual(len(store.events_for("13.0")), 3)


class TimelineOrderingTests(unittest.TestCase):
    def test_match_from_job_ad_is_merged_chronologically(self):
        timeline = build_timeline(job_ad(), parse_event_log(SUCCESS_LOG))
        kinds = [event.kind for event in timeline]
        self.assertEqual(kinds.index("MATCHED"), 1)
        self.assertEqual(timeline[1].source, "job_ad")
        self.assertEqual(timeline[1].host, "slot1@condor-worker-1-0")
        self.assertEqual([event.sequence for event in timeline], list(range(1, len(timeline) + 1)))

    def test_same_second_ties_keep_log_order_and_lifecycle_rank(self):
        ad = job_ad(QDate=None, LastMatchTime=BASE + 9)
        timeline = build_timeline(ad, parse_event_log(SUCCESS_LOG))
        kinds = [event.kind for event in timeline]
        # Matched at 10:20:24 is ranked before the execute event recorded in the same second.
        self.assertLess(kinds.index("MATCHED"), kinds.index("EXECUTION_STARTED"))
        # Output transfer finished and terminate share 10:22:08 and stay in log order.
        self.assertLess(kinds.index("OUTPUT_TRANSFER_FINISHED"), kinds.index("TERMINATED"))
        timestamps = [event.timestamp for event in timeline]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_timeline_falls_back_to_job_ad_without_event_log(self):
        timeline = build_timeline(job_ad(), [])
        self.assertEqual([(e.kind, e.source) for e in timeline], [("SUBMITTED", "job_ad"), ("MATCHED", "job_ad")])


if __name__ == "__main__":
    unittest.main()
