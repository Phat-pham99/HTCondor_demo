# HTCondor On-Demand Local Docker Cluster: Quick Demo Architecture

## 1. Executive Overview

This repository provides a zero-cost, fully local demonstration of an **HTCondor High-Throughput Computing (HTC) Cluster** using Docker Compose. An always-on **Central Manager** accepts workload batches while a local **Autoscaler Daemon** monitors job queue depth and dynamically provisions/teardowns **Worker Containers** using the local Docker daemon socket (`/var/run/docker.sock`).

                            +-------------------------------------------+
                            |          Local Docker Network             |
                            |               (condor-net)                |
                            +---------------------+---------------------+
                                                  |
              +-----------------------------------+-----------------------------------+
              |                                   |                                   |
              v                                   v                                   v
+---------------------------+       +---------------------------+       +---------------------------+
|   condor-manager (Co)     |       |   condor-autoscaler (Py)  |       |   condor-worker-X (Worker)|
| - Central Collector       |       | - Listens to schedd queue |       | - Dynamic condor_startd   |
| - Negotiator & Schedd     |       | - Talks to Docker Socket  |       | - Auto-exits when idle    |
| - Shared Volume (/out)    |       | - Spawns worker containers|       | - Mounts Shared Volume    |
+---------------------------+       +---------------------------+       +---------------------------+

---

## 2. Repository Layout (`htcondor-local-demo`)

```text
htcondor-local-demo/
├── docker-compose.yml              # Base orchestration for Manager & Autoscaler
├── CONDOR_PLAN_LOCAL.md            # Architecture spec & guide
├── config/
│   ├── condor_config.manager       # HTCondor Manager & Schedd daemon config
│   └── condor_config.worker        # Execution Node config with idle auto-exit
├── images/
│   ├── Dockerfile.manager          # Image for Central Manager
│   └── Dockerfile.worker           # Image for Execution Worker Nodes
├── autoscaler/
│   ├── condor_docker_autoscaler.py # Python script using docker-py & HTCondor CLI
│   └── requirements.txt            # Python dependencies (docker, htcondor)
├── workload_demo/
│   ├── monte_carlo_pi.py           # Distributed computational workload script
│   ├── job.sub                     # HTCondor batch submit file
│   └── output/                     # Shared volume for task output logs
└── run_demo.sh                     # One-click execution script