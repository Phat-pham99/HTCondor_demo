import type { FailureStage, JobState, NodeState, OutputStatus } from "../types/api";

export function formatTimestamp(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toDateString() === new Date().toDateString() ? date.toLocaleTimeString() : date.toLocaleString();
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatMemory(mb: number | null | undefined): string {
  if (mb === null || mb === undefined) return "—";
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
}

export const JOB_STATE_LABELS: Record<JobState, string> = {
  IDLE: "Queued",
  RUNNING: "Running",
  TRANSFERRING_OUTPUT: "Transferring output",
  COMPLETED: "Completed",
  FAILED: "Failed",
  HELD: "Held",
  REMOVED: "Removed",
  UNKNOWN: "Unknown",
};

export const OUTPUT_STATUS_LABELS: Record<OutputStatus, string> = {
  PENDING: "Pending",
  AVAILABLE: "Available",
  PARTIAL: "Partial",
  MISSING: "Missing",
  NONE_DECLARED: "None declared",
  UNKNOWN: "Unknown",
};

export const NODE_STATE_LABELS: Record<NodeState, string> = {
  AVAILABLE: "Available",
  CLAIMED: "Claimed",
  UNAVAILABLE: "Unavailable",
  OFFLINE: "Offline",
};

export const FAILURE_STAGE_LABELS: Record<FailureStage, string> = {
  QUEUE: "While waiting in the queue",
  INPUT_TRANSFER: "Input transfer",
  EXECUTION: "Execution",
  OUTPUT_TRANSFER: "Output transfer",
};
