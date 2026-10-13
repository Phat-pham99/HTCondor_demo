import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.condor_source import PoolData, SourceUnavailable
from app.services.events import EventStore
from app.services.monitor import Monitor
from app.services.outputs import OutputInspector
from fixtures import BASE, FAILED_LOG, SUCCESS_LOG, job_ad, slot_ad


class FakeSource:
    def __init__(self, pool):
        self.pool = pool
        self.fail = False
        self.extra = {}

    def fetch(self, history_limit):
        if self.fail:
            raise SourceUnavailable("collector down")
        return self.pool

    def find_job(self, cluster_id, proc_id):
        if self.fail:
            raise SourceUnavailable("collector down")
        return self.extra.get((cluster_id, proc_id))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        out = root / "out"
        out.mkdir()
        (out / "pi-12-0.json").write_text('{"pi": 3.14}\n')
        (out / "pi-12-0.log").write_text("")
        event_log = root / "EventLog"
        event_log.write_text(SUCCESS_LOG + FAILED_LOG)

        def ad(cluster, proc=0, **overrides):
            return job_ad(cluster, proc, OutputDirectory=str(out), Out=str(out / f"pi-{cluster}-{proc}.log"),
                          Err=str(out / f"pi-{cluster}-{proc}.err"), **overrides)

        pool = PoolData(
            queue=[
                ad(15, JobStatus=1, LastMatchTime=None, JobStartDate=None, JobCurrentStartDate=None,
                   CompletionDate=None, LastRemoteHost=None, ExitCode=None, RequestMemory=1048576),
                ad(16, JobStatus=2, RemoteHost="slot1@condor-worker-2-0", CompletionDate=None, ExitCode=None),
                ad(14, JobStatus=5, HoldReasonCode=12, HoldReason="Transfer output files failure", ExitCode=None),
            ],
            history=[ad(12), ad(13, ExitCode=1, TransferOutput=None, LastRemoteHost="slot1@condor-worker-2-0")],
            startd=[
                slot_ad("slot1@condor-worker-2-0", "Claimed", "Busy", JobId="16.0"),
                slot_ad("slot1@condor-manager"),
            ],
        )
        self.source = FakeSource(pool)
        self.source.extra[(1, 0)] = ad(1)
        settings = Settings(output_root=out, event_log_path=event_log, cache_seconds=0)
        monitor = Monitor(self.source, EventStore(event_log), OutputInspector(out), settings,
                          clock=lambda: BASE + 300)
        self.client = TestClient(create_app(monitor))

    def tearDown(self):
        self.directory.cleanup()

    def test_summary_counts(self):
        body = self.client.get("/api/cluster/summary").json()
        self.assertEqual(body["jobs"]["idle"], 1)
        self.assertEqual(body["jobs"]["running"], 1)
        self.assertEqual(body["jobs"]["completed"], 1)
        self.assertEqual(body["jobs"]["failed"], 1)
        self.assertEqual(body["jobs"]["held"], 1)
        self.assertEqual(body["nodes"], {"total": 2, "busy": 1, "available": 1, "unavailable": 0, "offline": 1})
        self.assertTrue(body["event_log_available"])
        self.assertEqual(body["recent_activity"][0]["kind"], "HELD")

    def test_job_filters(self):
        def ids(state):
            return [job["id"] for job in self.client.get(f"/api/jobs?state={state}").json()["jobs"]]

        self.assertEqual(ids("all"), ["16.0", "15.0", "14.0", "13.0", "12.0"])
        self.assertEqual(ids("queued"), ["15.0"])
        self.assertEqual(ids("running"), ["16.0"])
        self.assertEqual(ids("completed"), ["12.0"])
        self.assertEqual(ids("failed"), ["14.0", "13.0"])
        self.assertEqual(self.client.get("/api/jobs?state=bogus").status_code, 422)

    def test_job_detail_events_and_output(self):
        detail = self.client.get("/api/jobs/12/0").json()
        self.assertEqual(detail["state"], "COMPLETED")
        self.assertEqual(detail["output_status"], "AVAILABLE")
        self.assertTrue(detail["output_returned"])
        self.assertEqual(detail["raw"]["GlobalJobId"], f"condor-manager#12.0#{BASE}")
        events = self.client.get("/api/jobs/12/0/events").json()["events"]
        self.assertEqual(events[0]["kind"], "SUBMITTED")
        self.assertEqual(events[-1]["kind"], "TERMINATED")
        output = self.client.get("/api/jobs/12/0/output").json()
        result = next(item for item in output["files"] if item["role"] == "result")
        self.assertEqual(result["preview"], '{"pi": 3.14}\n')

    def test_old_job_is_found_through_direct_history_lookup(self):
        self.assertEqual(self.client.get("/api/jobs/1/0").json()["id"], "1.0")
        self.assertEqual(self.client.get("/api/jobs/99/0").status_code, 404)

    def test_nodes_include_offline_history_nodes(self):
        nodes = {node["name"]: node for node in self.client.get("/api/nodes").json()["nodes"]}
        self.assertEqual(nodes["condor-worker-2-0"]["state"], "CLAIMED")
        self.assertEqual(nodes["condor-worker-2-0"]["running_jobs"], ["16.0"])
        self.assertEqual(nodes["condor-worker-2-0"]["completed_jobs"], 1)
        self.assertEqual(nodes["condor-worker-1-0"]["state"], "OFFLINE")

    def test_htcondor_outage_is_reported_as_503(self):
        self.source.fail = True
        response = self.client.get("/api/cluster/summary")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "htcondor_unavailable")

    def test_invalid_job_ids_are_rejected(self):
        self.assertEqual(self.client.get("/api/jobs/-1/0").status_code, 422)
        self.assertEqual(self.client.get("/api/jobs/abc/0").status_code, 422)


if __name__ == "__main__":
    unittest.main()
