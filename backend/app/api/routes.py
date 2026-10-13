from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path, Query, Request

from app.models import ClusterSummary, JobDetail, JobEvents, JobFilter, JobList, JobOutput, NodeList
from app.services.monitor import Monitor

router = APIRouter(prefix="/api")

ClusterId = Path(ge=0, le=2**31 - 1)
ProcId = Path(ge=0, le=2**31 - 1)


def _monitor(request: Request) -> Monitor:
    return request.app.state.monitor


def _found(value, cluster_id: int, proc_id: int):
    if value is None:
        raise HTTPException(status_code=404, detail=f"Job {cluster_id}.{proc_id} was not found in the queue or history")
    return value


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/cluster/summary", response_model=ClusterSummary)
def cluster_summary(request: Request) -> ClusterSummary:
    return _monitor(request).summary()


@router.get("/nodes", response_model=NodeList)
def list_nodes(request: Request) -> NodeList:
    return _monitor(request).nodes()


@router.get("/jobs", response_model=JobList)
def list_jobs(request: Request, state: JobFilter = Query("all")) -> JobList:
    return _monitor(request).jobs(state)


@router.get("/jobs/{cluster_id}/{process_id}", response_model=JobDetail)
def job_detail(request: Request, cluster_id: int = ClusterId, process_id: int = ProcId) -> JobDetail:
    return _found(_monitor(request).job_detail(cluster_id, process_id), cluster_id, process_id)


@router.get("/jobs/{cluster_id}/{process_id}/events", response_model=JobEvents)
def job_events(request: Request, cluster_id: int = ClusterId, process_id: int = ProcId) -> JobEvents:
    return _found(_monitor(request).job_events(cluster_id, process_id), cluster_id, process_id)


@router.get("/jobs/{cluster_id}/{process_id}/output", response_model=JobOutput)
def job_output(request: Request, cluster_id: int = ClusterId, process_id: int = ProcId) -> JobOutput:
    return _found(_monitor(request).job_output(cluster_id, process_id), cluster_id, process_id)
