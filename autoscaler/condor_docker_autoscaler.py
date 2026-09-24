#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Protocol

try:
    import docker
    import paramiko
except ModuleNotFoundError:
    docker = None
    paramiko = None

LOGGER = logging.getLogger("condor-autoscaler")
WORKER_LABEL = "htcondor.autoscaler"
ROLE_LABEL = "htcondor.role"


@dataclass(frozen=True)
class Settings:
    manager_host: str
    ssh_user: str
    ssh_key_path: str
    known_hosts_path: str
    docker_network: str
    worker_image: str
    output_volume: str
    max_workers: int
    min_workers: int
    jobs_per_worker: int
    poll_seconds: int
    idle_seconds: int
    worker_cpus: int
    worker_memory_mb: int

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            manager_host=os.getenv("AUTOSCALER_MANAGER_HOST", "condor-manager"),
            ssh_user=os.getenv("AUTOSCALER_SSH_USER", "condor"),
            ssh_key_path=os.getenv("AUTOSCALER_SSH_KEY_PATH", "/run/ssh/id_ed25519"),
            known_hosts_path=os.getenv("AUTOSCALER_KNOWN_HOSTS_PATH", "/run/ssh/known_hosts"),
            docker_network=os.getenv("AUTOSCALER_DOCKER_NETWORK", "condor-net"),
            worker_image=os.getenv("AUTOSCALER_WORKER_IMAGE", "htcondor-demo-worker"),
            output_volume=os.getenv("AUTOSCALER_OUTPUT_VOLUME", "htcondor-demo-output"),
            max_workers=int(os.getenv("AUTOSCALER_MAX_WORKERS", "4")),
            min_workers=int(os.getenv("AUTOSCALER_MIN_WORKERS", "1")),
            jobs_per_worker=int(os.getenv("AUTOSCALER_JOBS_PER_WORKER", "1")),
            poll_seconds=int(os.getenv("AUTOSCALER_POLL_SECONDS", "5")),
            idle_seconds=int(os.getenv("AUTOSCALER_IDLE_SECONDS", "60")),
            worker_cpus=int(os.getenv("AUTOSCALER_WORKER_CPUS", "1")),
            worker_memory_mb=int(os.getenv("AUTOSCALER_WORKER_MEMORY_MB", "512")),
        )

    def validate(self) -> None:
        if self.max_workers < 1 or self.min_workers < 0 or self.min_workers > self.max_workers:
            raise ValueError("worker limits must satisfy 0 <= min <= max and max >= 1")
        if self.jobs_per_worker < 1:
            raise ValueError("jobs per worker must be positive")
        if self.poll_seconds < 1 or self.idle_seconds < 0:
            raise ValueError("poll and idle intervals must be non-negative")


class CommandRunner(Protocol):
    def run(self, command: str) -> str:
        ...


class SSHCommandRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        if os.path.exists(settings.known_hosts_path):
            self.client.load_host_keys(settings.known_hosts_path)
        else:
            LOGGER.warning("known_hosts file is unavailable; using temporary host-key acceptance")
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.client.connect(
            hostname=settings.manager_host,
            username=settings.ssh_user,
            key_filename=settings.ssh_key_path,
            look_for_keys=False,
            allow_agent=False,
            timeout=10,
        )

    def run(self, command: str) -> str:
        _, stdout, stderr = self.client.exec_command(command, timeout=15)
        output = stdout.read().decode("utf-8", errors="replace")
        error = stderr.read().decode("utf-8", errors="replace")
        status = stdout.channel.recv_exit_status()
        if status != 0:
            raise RuntimeError(f"command failed ({status}): {command}: {error.strip()}")
        return output

    def close(self) -> None:
        self.client.close()


def parse_total(output: str) -> int:
    match = re.search(
        r"^\s*total(?:\s+for\s+(?:query|all users):)?\s+(\d+)",
        output,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if match is None:
        raise ValueError(f"could not find total in HTCondor output: {output!r}")
    return int(match.group(1))


def read_demand(runner: CommandRunner) -> int:
    queued = parse_total(runner.run("condor_q -name condor-manager@condor-manager -total"))
    running = parse_total(runner.run("condor_status -total"))
    return queued + running


def desired_workers(demand: int, settings: Settings) -> int:
    if demand <= 0:
        return 0
    calculated = math.ceil(demand / settings.jobs_per_worker)
    return min(settings.max_workers, max(settings.min_workers, calculated))


class WorkerController:
    def __init__(self, docker_client: docker.DockerClient, settings: Settings) -> None:
        self.docker_client = docker_client
        self.settings = settings
        self.idle_since: float | None = None

    def worker_containers(self, all_containers: bool = True) -> list[docker.models.containers.Container]:
        return self.docker_client.containers.list(
            all=all_containers,
            filters={"label": f"{WORKER_LABEL}=true"},
        )

    def remove(self, container: docker.models.containers.Container) -> None:
        LOGGER.info("removing worker %s", container.name)
        try:
            container.remove(force=True)
        except docker.errors.APIError:
            LOGGER.exception("could not remove worker %s", container.name)

    def create(self, index: int) -> None:
        name = f"condor-worker-{int(time.time())}-{index}"
        LOGGER.info("creating worker %s", name)
        self.docker_client.containers.run(
            self.settings.worker_image,
            name=name,
            hostname=name,
            detach=True,
            network=self.settings.docker_network,
            environment={
                "CONDOR_HOST": "condor-manager",
                "WORKER_IDLE_SECONDS": str(self.settings.idle_seconds),
            },
            volumes={self.settings.output_volume: {"bind": "/out", "mode": "rw"}},
            labels={
                WORKER_LABEL: "true",
                ROLE_LABEL: "worker",
            },
            mem_limit=f"{self.settings.worker_memory_mb}m",
            nano_cpus=self.settings.worker_cpus * 1_000_000_000,
            cap_drop=["ALL"],
            security_opt=["no-new-privileges:true"],
        )

    def reconcile(self, demand: int) -> None:
        containers = self.worker_containers()
        running = [container for container in containers if container.status == "running"]
        stopped = [container for container in containers if container.status != "running"]
        for container in stopped:
            self.remove(container)

        if demand > 0:
            self.idle_since = None
            target = desired_workers(demand, self.settings)
        else:
            now = time.monotonic()
            if self.idle_since is None:
                self.idle_since = now
            elapsed = now - self.idle_since
            target = len(running) if elapsed < self.settings.idle_seconds else 0

        if len(running) < target:
            for index in range(target - len(running)):
                self.create(index)
        elif len(running) > target:
            for container in running[target:]:
                self.remove(container)

    def remove_all(self) -> None:
        for container in self.worker_containers():
            self.remove(container)


def run(settings: Settings, once: bool = False) -> None:
    settings.validate()
    if docker is None or paramiko is None:
        raise RuntimeError("docker and paramiko are required to run the autoscaler")
    runner = SSHCommandRunner(settings)
    docker_client = docker.from_env()
    controller = WorkerController(docker_client, settings)
    try:
        while True:
            demand = read_demand(runner)
            LOGGER.info("queue and running demand: %d", demand)
            controller.reconcile(demand)
            if once:
                return
            time.sleep(settings.poll_seconds)
    finally:
        runner.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(Settings.from_environment(), once=args.once)


if __name__ == "__main__":
    main()
