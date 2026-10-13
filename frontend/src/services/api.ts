import type { ClusterSummary, JobDetail, JobEvents, JobFilter, JobList, JobOutput, NodeList } from "../types/api";

/** Distinguishes monitoring failures from job failures. */
export type ApiErrorKind = "backend_unreachable" | "htcondor_unavailable" | "not_found" | "http";

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("backend_unreachable", "The dashboard backend cannot be reached.");
  }
  if (response.status === 503) {
    throw new ApiError("htcondor_unavailable", "The monitoring backend cannot query the HTCondor pool.", 503);
  }
  if (response.status === 502 || response.status === 504) {
    throw new ApiError("backend_unreachable", "The dashboard backend is not responding.", response.status);
  }
  if (response.status === 404) {
    throw new ApiError("not_found", "Not found in the HTCondor queue or history.", 404);
  }
  if (!response.ok) {
    throw new ApiError("http", `Request failed with HTTP ${response.status}.`, response.status);
  }
  return (await response.json()) as T;
}

function jobPath(jobId: string): string {
  const [cluster, proc] = jobId.split(".").map((part) => encodeURIComponent(part));
  return `/api/jobs/${cluster}/${proc}`;
}

export const api = {
  summary: (signal?: AbortSignal) => getJson<ClusterSummary>("/api/cluster/summary", signal),
  nodes: (signal?: AbortSignal) => getJson<NodeList>("/api/nodes", signal),
  jobs: (filter: JobFilter, signal?: AbortSignal) =>
    getJson<JobList>(`/api/jobs?state=${encodeURIComponent(filter)}`, signal),
  job: (jobId: string, signal?: AbortSignal) => getJson<JobDetail>(jobPath(jobId), signal),
  events: (jobId: string, signal?: AbortSignal) => getJson<JobEvents>(`${jobPath(jobId)}/events`, signal),
  output: (jobId: string, signal?: AbortSignal) => getJson<JobOutput>(`${jobPath(jobId)}/output`, signal),
};
