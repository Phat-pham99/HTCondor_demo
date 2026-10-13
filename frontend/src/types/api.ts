export type JobState =
  | "IDLE"
  | "RUNNING"
  | "TRANSFERRING_OUTPUT"
  | "COMPLETED"
  | "FAILED"
  | "HELD"
  | "REMOVED"
  | "UNKNOWN";
export type OutputStatus = "PENDING" | "AVAILABLE" | "PARTIAL" | "MISSING" | "NONE_DECLARED" | "UNKNOWN";
export type NodeState = "AVAILABLE" | "CLAIMED" | "UNAVAILABLE" | "OFFLINE";
export type FailureStage = "QUEUE" | "INPUT_TRANSFER" | "EXECUTION" | "OUTPUT_TRANSFER";
export type StepStatus = "DONE" | "CURRENT" | "PENDING" | "FAILED" | "SKIPPED";
export type JobFilter = "all" | "queued" | "running" | "completed" | "failed";

export interface Job {
  id: string;
  cluster_id: number;
  proc_id: number;
  global_job_id: string | null;
  owner: string | null;
  state: JobState;
  raw_status: string | null;
  raw_status_code: number | null;
  submitted_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  node: string | null;
  slot: string | null;
  queue_wait_seconds: number | null;
  runtime_seconds: number | null;
  exit_code: number | null;
  output_status: OutputStatus;
  command: string | null;
  source: "queue" | "history";
}

export interface LifecycleStep {
  key: string;
  label: string;
  status: StepStatus;
  timestamp: string | null;
  detail: string | null;
}

export interface JobDetail extends Job {
  arguments: string | null;
  current_stage: string;
  matched_at: string | null;
  exit_by_signal: boolean | null;
  exit_signal: number | null;
  hold_reason: string | null;
  hold_reason_code: number | null;
  failure_stage: FailureStage | null;
  failure_reason: string | null;
  output_returned: boolean | null;
  request_cpus: number | null;
  request_memory_mb: number | null;
  requirements: string | null;
  job_starts: number | null;
  lifecycle: LifecycleStep[];
  raw: Record<string, unknown>;
}

export interface JobEvent {
  sequence: number;
  timestamp: string;
  code: number | null;
  kind: string;
  title: string;
  detail: string | null;
  host: string | null;
  source: "event_log" | "job_ad";
}

export interface JobEvents {
  job_id: string;
  event_log_available: boolean;
  events: JobEvent[];
}

export interface OutputFile {
  role: "result" | "stdout" | "stderr";
  name: string;
  path: string;
  exists: boolean | null;
  size_bytes: number | null;
  modified_at: string | null;
  preview: string | null;
  truncated: boolean;
  note: string | null;
}

export interface JobOutput {
  job_id: string;
  status: OutputStatus;
  returned: boolean | null;
  files: OutputFile[];
}

export interface Slot {
  name: string;
  state: string | null;
  activity: string | null;
  slot_type: string | null;
  job_id: string | null;
  cpus: number | null;
  memory_mb: number | null;
}

export interface ComputeNode {
  name: string;
  state: NodeState;
  raw_state: string | null;
  slots: Slot[];
  running_jobs: string[];
  cpus_total: number | null;
  cpus_allocated: number;
  memory_total_mb: number | null;
  memory_allocated_mb: number;
  completed_jobs: number;
  last_update: string | null;
}

export interface ClusterSummary {
  collected_at: string;
  jobs: {
    idle: number;
    running: number;
    transferring_output: number;
    completed: number;
    failed: number;
    held: number;
    removed: number;
    unknown: number;
    total: number;
  };
  nodes: { total: number; busy: number; available: number; unavailable: number; offline: number };
  recent_activity: { timestamp: string; job_id: string; kind: string; title: string; host: string | null }[];
  event_log_available: boolean;
  history_limit: number;
}

export interface JobList {
  collected_at: string;
  filter: JobFilter;
  jobs: Job[];
}

export interface NodeList {
  collected_at: string;
  nodes: ComputeNode[];
}
