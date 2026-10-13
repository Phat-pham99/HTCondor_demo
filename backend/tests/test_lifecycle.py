import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.models import FailureStage, JobState, OutputStatus, StepStatus
from app.services.events import parse_event_log
from app.services.lifecycle import build_job_detail, build_timeline
from app.services.normalize import build_job, normalize_job_state
from app.services.outputs import OutputInspector
from fixtures import BASE, FAILED_LOG, SUCCESS_LOG, job_ad

NOW = datetime.fromtimestamp(BASE + 200, tz=timezone.utc)


def detail_for(ad, log="", output_status=OutputStatus.AVAILABLE):
    job = build_job(ad, now=NOW, source="history", output_status=output_status)
    events = [event for event in parse_event_log(log) if event.job_id == job.id]
    return build_job_detail(job, ad, build_timeline(ad, events))


def statuses(detail):
    return {step.key: step.status for step in detail.lifecycle}


class LifecycleTests(unittest.TestCase):
    def test_successful_job_completes_every_step(self):
        detail = detail_for(job_ad(), SUCCESS_LOG)
        self.assertTrue(all(status == StepStatus.DONE for status in statuses(detail).values()))
        self.assertTrue(detail.output_returned)
        self.assertIsNone(detail.failure_stage)
        self.assertEqual(detail.current_stage, "Completed successfully")
        finished = next(step for step in detail.lifecycle if step.key == "FINISHED")
        self.assertEqual(finished.timestamp, datetime(2026, 10, 13, 10, 22, 7, tzinfo=timezone.utc))

    def test_idle_job_is_waiting_in_queue(self):
        ad = job_ad(JobStatus=1, LastMatchTime=None, JobStartDate=None, JobCurrentStartDate=None,
                    CompletionDate=None, LastRemoteHost=None, ExitCode=None, NumJobStarts=0)
        detail = detail_for(ad, output_status=OutputStatus.PENDING)
        self.assertEqual(statuses(detail)["QUEUED"], StepStatus.CURRENT)
        self.assertEqual(statuses(detail)["MATCHED"], StepStatus.PENDING)
        self.assertIsNone(detail.output_returned)

    def test_nonzero_exit_fails_during_execution(self):
        ad = job_ad(13, ExitCode=1, TransferOutput=None, LastRemoteHost="slot1@condor-worker-2-0")
        detail = detail_for(ad, FAILED_LOG, OutputStatus.NONE_DECLARED)
        self.assertEqual(detail.state, JobState.FAILED)
        self.assertEqual(detail.failure_stage, FailureStage.EXECUTION)
        self.assertEqual(detail.failure_reason, "Exited with code 1")
        self.assertEqual(statuses(detail)["FINISHED"], StepStatus.FAILED)
        self.assertEqual(statuses(detail)["OUTPUT_RETURNED"], StepStatus.SKIPPED)

    def test_output_transfer_hold_is_attributed_to_output_stage(self):
        ad = job_ad(14, JobStatus=5, HoldReasonCode=12, HoldReason="Transfer output files failure", ExitCode=None)
        detail = detail_for(ad, FAILED_LOG, OutputStatus.MISSING)
        self.assertEqual(detail.failure_stage, FailureStage.OUTPUT_TRANSFER)
        self.assertFalse(detail.output_returned)
        self.assertEqual(statuses(detail)["OUTPUT_RETURNED"], StepStatus.FAILED)
        self.assertEqual(statuses(detail)["FINISHED"], StepStatus.DONE)

    def test_removed_before_matching_fails_in_queue(self):
        ad = job_ad(JobStatus=3, LastMatchTime=None, JobStartDate=None, JobCurrentStartDate=None,
                    NumJobStarts=0, ExitCode=None, RemoveReason="via condor_rm (by user demo)")
        detail = detail_for(ad, output_status=OutputStatus.MISSING)
        self.assertEqual(detail.failure_stage, FailureStage.QUEUE)
        self.assertEqual(statuses(detail)["QUEUED"], StepStatus.FAILED)
        self.assertEqual(statuses(detail)["RUNNING"], StepStatus.SKIPPED)


class OutputInspectorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "out"
        self.root.mkdir()
        self.inspector = OutputInspector(self.root, preview_bytes=8)

    def tearDown(self):
        self.directory.cleanup()

    def ad(self, **overrides):
        values = {"OutputDirectory": str(self.root), "Out": str(self.root / "pi-12-0.log"),
                  "Err": str(self.root / "pi-12-0.err")}
        return job_ad(**{**values, **overrides})

    def test_available_partial_and_missing(self):
        (self.root / "a.json").write_text("{}")
        files = self.inspector.describe(self.ad(TransferOutput="a.json"))
        self.assertEqual(self.inspector.status(JobState.COMPLETED, files), OutputStatus.AVAILABLE)
        files = self.inspector.describe(self.ad(TransferOutput="a.json, b.json"))
        self.assertEqual(self.inspector.status(JobState.COMPLETED, files), OutputStatus.PARTIAL)
        files = self.inspector.describe(self.ad(TransferOutput="b.json"))
        self.assertEqual(self.inspector.status(JobState.COMPLETED, files), OutputStatus.MISSING)
        self.assertEqual(self.inspector.status(JobState.RUNNING, files), OutputStatus.PENDING)
        files = self.inspector.describe(self.ad(TransferOutput=None))
        self.assertEqual(self.inspector.status(JobState.FAILED, files), OutputStatus.NONE_DECLARED)

    def test_paths_outside_root_are_never_read(self):
        secret = Path(self.directory.name) / "secret.txt"
        secret.write_text("do not read")
        os.symlink(secret, self.root / "link.txt")
        files = self.inspector.describe(
            self.ad(TransferOutput="../secret.txt, link.txt", Err="/etc/passwd"), include_preview=True
        )
        for item in files:
            if item.name in ("../secret.txt", "link.txt", "/etc/passwd"):
                self.assertIsNone(item.exists, item.name)
                self.assertIsNone(item.preview)
        self.assertEqual(self.inspector.status(JobState.COMPLETED, files), OutputStatus.UNKNOWN)

    def test_preview_is_tail_limited(self):
        (self.root / "pi-12-0.err").write_text("0123456789abcdef")
        files = self.inspector.describe(self.ad(), include_preview=True)
        stderr = next(item for item in files if item.role == "stderr")
        self.assertEqual((stderr.preview, stderr.truncated, stderr.size_bytes), ("89abcdef", True, 16))


if __name__ == "__main__":
    unittest.main()
