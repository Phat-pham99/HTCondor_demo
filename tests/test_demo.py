import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "autoscaler"))
sys.path.insert(0, str(Path(__file__).parents[1] / "workload_demo"))

from condor_docker_autoscaler import Settings, desired_workers, parse_total
from monte_carlo_pi import estimate_pi, write_result


class AutoscalerTests(unittest.TestCase):
    def settings(self, max_workers=4, min_workers=1, jobs_per_worker=1):
        return Settings(
            manager_host="manager",
            ssh_user="condor",
            ssh_key_path="key",
            known_hosts_path="known_hosts",
            docker_network="network",
            worker_image="worker",
            output_volume="output",
            max_workers=max_workers,
            min_workers=min_workers,
            jobs_per_worker=jobs_per_worker,
            poll_seconds=1,
            idle_seconds=60,
            worker_cpus=1,
            worker_memory_mb=512,
        )

    def test_parse_total_accepts_condor_q_output(self):
        self.assertEqual(parse_total("total 3\n"), 3)

    def test_desired_workers_scales_and_caps(self):
        settings = self.settings()
        self.assertEqual(desired_workers(0, settings), 0)
        self.assertEqual(desired_workers(3, settings), 3)
        self.assertEqual(desired_workers(8, settings), 4)

    def test_desired_workers_uses_jobs_per_worker(self):
        settings = self.settings(jobs_per_worker=2)
        self.assertEqual(desired_workers(5, settings), 3)


class WorkloadTests(unittest.TestCase):
    def test_estimate_pi_is_in_expected_range(self):
        estimate = estimate_pi(10_000, 7)
        self.assertGreater(estimate, 3.0)
        self.assertLess(estimate, 3.3)

    def test_write_result_contains_requested_parameters(self):
        import json

        with self.subTest("result file"):
            path = Path(self.id().replace(".", "-") + ".json")
            try:
                estimate = write_result(path, 1_000, 3)
                payload = json.loads(path.read_text())
                self.assertEqual(payload["samples"], 1_000)
                self.assertEqual(payload["seed"], 3)
                self.assertEqual(payload["pi"], estimate)
            finally:
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
