# HTCondor On-Demand Local Docker Cluster

## Purpose

This repository is a local Docker Compose demonstration of an HTCondor pool. The manager is an all-in-one pool service containing the collector, negotiator, schedd, and startd. The autoscaler observes queued and running work over SSH, creates labeled execution containers through the Docker API, and tears down workers after the idle grace period.

## Architecture

```text
                         local Docker network
                    +---------------------------+
                    | condor-manager             |
                    | collector, negotiator,     |
                    | schedd, startd, sshd       |
                    +-------------+-------------+
                                  |
                    +-------------+-------------+
                    | condor-autoscaler          |
                    | SSH queue queries           |
                    | Docker API worker lifecycle |
                    +-------------+-------------+
                                  |
                    +-------------+-------------+
                    | condor-worker-X             |
                    | startd, work directory,    |
                    | shared /out volume          |
                    +---------------------------+
```

## Implemented decisions

- Target: Linux Docker Engine with Docker Compose v2.
- Images: official `htcondor/mini:lts` and `htcondor/execute:lts` bases.
- Scaling: dynamic, demand-based, one worker per job by default, capped at four.
- Demand: queued jobs plus running jobs.
- Teardown: workers are removed after 60 seconds without demand.
- Observation: the autoscaler uses `condor_q -total` and `condor_status -total` over SSH.
- Workloads: executable and inputs are transferred by HTCondor; output JSON files are transferred to the shared named `/out` volume.
- Verification: `run_demo.sh` verifies output files and removes containers, network, and volume.
- Privilege: the autoscaler runs as the host UID and Docker socket GID, drops capabilities, and enables `no-new-privileges`.

## Repository layout

```text
.
├── docker-compose.yml
├── CONDOR_PLAN_LOCAL.md
├── config/
│   ├── condor_config.manager
│   └── condor_config.worker
├── images/
│   ├── Dockerfile.manager
│   ├── Dockerfile.worker
│   ├── manager-entrypoint.sh
│   └── worker-entrypoint.sh
├── autoscaler/
│   ├── Dockerfile
│   ├── condor_docker_autoscaler.py
│   └── requirements.txt
├── workload_demo/
│   ├── monte_carlo_pi.py
│   └── job.sub
├── tests/
│   └── test_demo.py
└── run_demo.sh
```

## Runtime flow

1. `run_demo.sh` creates a temporary SSH key and exposes its public key to the manager.
2. Compose builds the manager, autoscaler, and worker images.
3. The manager starts HTCondor and its SSH listener.
4. The autoscaler connects over SSH and polls queue and startd totals.
5. Four jobs are submitted through `workload_demo/job.sub`.
6. The autoscaler creates up to four labeled worker containers.
7. Each worker runs a Monte Carlo pi job and transfers its JSON result to `/out`.
8. The script verifies all four JSON files and tears down the local stack.
