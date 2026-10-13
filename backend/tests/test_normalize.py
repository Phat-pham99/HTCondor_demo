import unittest
from datetime import datetime, timedelta, timezone

from app.models import JobState, NodeState, OutputStatus
from app.services.normalize import (
    NodeRegistry,
    build_job,
    completed_counts,
    group_nodes,
    merge_job_ads,
    normalize_job_state,
)
from fixtures import BASE, job_ad, slot_ad

NOW = datetime.fromtimestamp(BASE + 200, tz=timezone.utc)


class JobStateTests(unittest.TestCase):
    def test_maps_every_htcondor_status(self):
        cases = {
            1: JobState.IDLE,
            2: JobState.RUNNING,
            3: JobState.REMOVED,
            4: JobState.COMPLETED,
            5: JobState.HELD,
            6: JobState.TRANSFERRING_OUTPUT,
            7: JobState.RUNNING,
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(normalize_job_state({"JobStatus": code, "ExitCode": 0}), expected)

    def test_completed_with_nonzero_exit_is_failed(self):
        self.assertEqual(normalize_job_state({"JobStatus": 4, "ExitCode": 3}), JobState.FAILED)

    def test_completed_by_signal_is_failed(self):
        self.assertEqual(normalize_job_state({"JobStatus": 4, "ExitBySignal": True, "ExitSignal": 9}), JobState.FAILED)

    def test_malformed_or_missing_status_is_unknown(self):
        for value in (None, "garbage", 42, [1]):
            with self.subTest(value=value):
                self.assertEqual(normalize_job_state({"JobStatus": value}), JobState.UNKNOWN)

    def test_numeric_strings_are_accepted(self):
        self.assertEqual(normalize_job_state({"JobStatus": "2"}), JobState.RUNNING)


class BuildJobTests(unittest.TestCase):
    def test_completed_job_durations_and_node(self):
        job = build_job(job_ad(), now=NOW, source="history", output_status=OutputStatus.AVAILABLE)
        self.assertEqual(job.id, "12.0")
        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertEqual(job.raw_status, "Completed")
        self.assertEqual(job.node, "condor-worker-1-0")
        self.assertEqual(job.slot, "slot1@condor-worker-1-0")
        self.assertEqual(job.queue_wait_seconds, 9)
        self.assertEqual(job.runtime_seconds, 104)
        self.assertEqual(job.exit_code, 0)

    def test_idle_job_reports_ongoing_wait_and_no_node(self):
        ad = job_ad(JobStatus=1, JobStartDate=None, JobCurrentStartDate=None, CompletionDate=None, ExitCode=None)
        job = build_job(ad, now=NOW, source="queue", output_status=OutputStatus.PENDING)
        self.assertEqual(job.queue_wait_seconds, 200)
        self.assertIsNone(job.runtime_seconds)
        self.assertIsNone(job.node)
        self.assertIsNone(job.exit_code)

    def test_running_job_runtime_uses_current_time(self):
        ad = job_ad(JobStatus=2, RemoteHost="slot1@condor-worker-1-0", CompletionDate=None)
        job = build_job(ad, now=NOW, source="queue", output_status=OutputStatus.PENDING)
        self.assertEqual(job.runtime_seconds, 191)
        self.assertEqual(job.node, "condor-worker-1-0")

    def test_missing_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            build_job({"JobStatus": 1}, now=NOW, source="queue", output_status=OutputStatus.PENDING)


class MergeTests(unittest.TestCase):
    def test_history_wins_over_stale_queue_entry(self):
        queue = [job_ad(JobStatus=2, EnteredCurrentStatus=BASE + 9)]
        history = [job_ad()]
        merged = merge_job_ads(queue, history)
        ad, origin = merged[(12, 0)]
        self.assertEqual(origin, "history")
        self.assertEqual(ad["JobStatus"], 4)

    def test_ads_without_ids_are_skipped(self):
        self.assertEqual(merge_job_ads([{"JobStatus": 1}], []), {})


class NodeTests(unittest.TestCase):
    def test_groups_slots_by_machine(self):
        ads = [
            slot_ad("slot1@worker-a", "Claimed", "Busy", JobId="12.0"),
            slot_ad("slot1@worker-b"),
            slot_ad("slot1@worker-c", "Owner", "Idle"),
        ]
        nodes = group_nodes(ads, {"worker-a": 2})
        self.assertEqual(nodes["worker-a"].state, NodeState.CLAIMED)
        self.assertEqual(nodes["worker-a"].running_jobs, ["12.0"])
        self.assertEqual(nodes["worker-a"].cpus_allocated, 1)
        self.assertEqual(nodes["worker-a"].completed_jobs, 2)
        self.assertEqual(nodes["worker-b"].state, NodeState.AVAILABLE)
        self.assertEqual(nodes["worker-b"].cpus_allocated, 0)
        self.assertEqual(nodes["worker-c"].state, NodeState.UNAVAILABLE)

    def test_partitionable_parent_is_not_counted_as_allocation(self):
        ads = [
            slot_ad("slot1@big", SlotType="Partitionable", Cpus=3, Memory=3000, TotalCpus=4, TotalMemory=4096),
            slot_ad("slot1_1@big", "Claimed", "Busy", SlotType="Dynamic", Cpus=1, Memory=1024,
                    TotalCpus=4, TotalMemory=4096, JobId="5.0"),
        ]
        node = group_nodes(ads, {})["big"]
        self.assertEqual(node.state, NodeState.CLAIMED)
        self.assertEqual((node.cpus_allocated, node.cpus_total), (1, 4))
        self.assertEqual((node.memory_allocated_mb, node.memory_total_mb), (1024, 4096))

    def test_registry_marks_vanished_nodes_offline_then_forgets_them(self):
        registry = NodeRegistry(retention_seconds=60)
        registry.update(group_nodes([slot_ad("slot1@worker-a")], {}), {}, NOW)
        nodes = registry.update({}, {}, NOW + timedelta(seconds=30))
        self.assertEqual([(n.name, n.state) for n in nodes], [("worker-a", NodeState.OFFLINE)])
        self.assertEqual(registry.update({}, {}, NOW + timedelta(seconds=120)), [])

    def test_completed_counts_only_count_finished_jobs(self):
        jobs = [
            build_job(job_ad(proc=0), now=NOW, source="history", output_status=OutputStatus.AVAILABLE),
            build_job(job_ad(proc=1, ExitCode=1), now=NOW, source="history", output_status=OutputStatus.MISSING),
            build_job(job_ad(proc=2, JobStatus=5), now=NOW, source="queue", output_status=OutputStatus.MISSING),
        ]
        self.assertEqual(completed_counts(jobs), {"condor-worker-1-0": 2})


if __name__ == "__main__":
    unittest.main()
