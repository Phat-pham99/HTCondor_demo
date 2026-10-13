
HTCondor Job Lifecycle Dashboard
Project Objective
Build a focused monitoring dashboard that visualizes the complete lifecycle of an HTCondor job:

```text
Job submitted
     ↓
Waiting in queue
     ↓
Matched with a compute node
     ↓
Running on the node
     ↓
Completed or failed
     ↓
Output returned to the submit machine
```

The first version should prioritize transparency and usability. It should help a user understand where a job is, which compute node is processing it, how long it waited and ran, and whether its output was returned successfully.
-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

MVP Scope

1. Cluster Overview
   Display:
   Number of idle jobs
   Number of running jobs
   Number of completed jobs
   Number of held or failed jobs
   Total compute nodes
   Busy versus available nodes
   Recent job activity
2. Job List
   For each job, display:
   Job ID
   Owner
   Current status
   Submission time
   Assigned compute node
   Runtime
   Result availability
   Provide filters for:
   All
   Queued
   Running
   Completed
   Failed or held
3. Job Detail and Lifecycle
   When a job is selected, show its lifecycle as a timeline, for example:

```text
10:20:15  Submitted
10:20:16  Added to queue
10:20:22  Matched with worker-02
10:20:24  Execution started
10:22:07  Execution completed
10:22:08  Output transferred
```

The detail view should answer:
Where is the job now?
Which node is executing or executed it?
How long did it wait in the queue?
How long did it run?
Was the output returned successfully?
If it failed, at which stage did it fail?
4. Compute-Node View
For each compute node, display:
Node name
Current state, such as available, claimed, or offline
Job currently running
Allocated CPU
Allocated memory
Number of completed jobs
Last update time
For the MVP, use attributes already available from HTCondor. Full host-level telemetry is not required.
-------------------------------------------------------------------------------------------------------

Recommended Architecture

```text
HTCondor Pool
├── Submit node
├── Central manager
└── Compute nodes
          │
          ▼
FastAPI monitoring backend
├── Query active job queue
├── Query job history
├── Query compute-node status
└── Parse job event logs
          │
          ▼
REST polling every 2–5 seconds
          │
          ▼
React and TypeScript dashboard
```

Recommended Technology Stack
Backend: Python and FastAPI
HTCondor integration: Python bindings where practical; CLI commands are acceptable for the initial prototype
Frontend: React and TypeScript
Updates: REST polling every 2–5 seconds
Storage: No database for the first version
Deployment: Docker Compose
Demonstration workload: A small Python computation that produces an output file
Polling is sufficient for the MVP. WebSockets and event-streaming infrastructure can be introduced later if they provide clear value.
-------------------------------------------------------------------------------------------------------------------------------------

Minimal Backend API

```text
GET /api/cluster/summary
GET /api/nodes
GET /api/jobs
GET /api/jobs/{cluster_id}/{process_id}
GET /api/jobs/{cluster_id}/{process_id}/events
GET /api/jobs/{cluster_id}/{process_id}/output
```

The backend should translate raw HTCondor data into a stable application-level JSON model. The frontend should not need to understand ClassAds or parse command-line output.
Normalized Job States

```text
IDLE
RUNNING
COMPLETED
HELD
FAILED
REMOVED
TRANSFERRING_OUTPUT
```

If HTCondor exposes a more detailed state, preserve the raw value in the API response while also returning one normalized state for the UI.
-------------------------------------------------------------------------------------------------------------------------------------------

Implementation Phases
Phase 1: Establish a Working HTCondor Pool
Configure one central manager.
Configure one submit node.
Configure two compute nodes.
Submit a simple Python job.
Confirm that the job enters the queue.
Confirm that a compute node executes it.
Confirm that the output file returns to the submit node.
Record the commands and configuration required to reproduce the environment.
Definition of done: A sample job completes successfully, and its output is transferred back to the submit node.
Phase 2: Build a Read-Only Monitoring Backend
Query active jobs.
Query completed and historical jobs.
Query compute-node states.
Read job lifecycle events.
Normalize job and node data.
Expose the required REST endpoints.
Handle missing, delayed, and malformed data safely.
Definition of done: The backend returns consistent JSON for queued, running, completed, and failed jobs, plus current compute-node information.
Phase 3: Build the Dashboard
Create the cluster summary cards.
Create the filterable job table.
Create compute-node cards or a node grid.
Create the job lifecycle timeline.
Present job output and error information.
Add loading, empty, unavailable, and error states.
Poll the backend every 2–5 seconds.
Definition of done: A user can follow a job from submission through execution and output retrieval without using the HTCondor command line.
Phase 4: Prepare the Demonstration
Demonstrate at least four scenarios:
A successful job
A long-running job
A failed job
A queued job waiting because no compute node is available
For each scenario, verify that the dashboard presents the correct state, node assignment, timestamps, lifecycle events, and output or error details.
Definition of done: The dashboard visibly distinguishes all four scenarios and tells a coherent end-to-end story.
-----------------------------------------------------------------------------------------------------------------

Out of Scope for Version 1
Do not add the following to the MVP:
AI-based scheduling
Carbon-emission estimates
Energy-aware scheduling
Kubernetes
Authentication and role-based access control
Multi-cluster federation
Predictive failure detection
Complex DAG workflows
OpenTelemetry
Full Prometheus and Grafana integration
Kafka or another event-streaming platform
A production-grade database
These features can be considered only after the basic job lifecycle is reliable and clearly visualized.
-------------------------------------------------------------------------------------------------------

Suggested Repository Structure

```text
htcondor-dashboard/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── services/
│   │   ├── models/
│   │   └── main.py
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── types/
│   ├── package.json
│   └── Dockerfile
├── condor/
│   ├── config/
│   ├── jobs/
│   └── examples/
├── docker-compose.yml
├── README.md
└── docs/
    ├── architecture.md
    └── demo-scenarios.md
```

---

Quality Requirements
Keep the interface read-only in the first version.
Do not fabricate unavailable metrics.
Show the last successful refresh time.
Preserve useful raw HTCondor identifiers for debugging.
Clearly distinguish a failed job from a monitoring or network failure.
Ensure that completed jobs remain visible through job history.
Avoid coupling frontend components directly to raw HTCondor fields.
Include reproducible setup and demonstration instructions.
Add backend tests for state normalization and event ordering.
-------------------------------------------------------------

Portfolio Positioning
Use this initial description:

> I built an observability dashboard that makes distributed-computing activity transparent by visualizing job submission, queueing, resource assignment, execution, failure, and result retrieval across an HTCondor cluster.
> Do not initially describe the project as AI-driven, carbon-aware, or green computing. Those claims should only be introduced after corresponding functionality and measurable evidence exist.
> The longer-term direction can be:
> First, make distributed computation visible. Then use that visibility to investigate resource efficiency and sustainability.

---

Future Extensions
After the MVP is stable, possible extensions include:
Node-utilization analysis
Idle-resource detection
Runtime and resource-efficiency comparisons
Historical trends
Prometheus metrics
Real-time updates through WebSockets
Energy-aware scheduling experiments
Carbon-aware workload timing
Authentication and access control
Multiple HTCondor pools
Each extension should be introduced as a separate, measurable iteration rather than bundled into the first release.
