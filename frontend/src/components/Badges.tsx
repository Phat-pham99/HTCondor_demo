import type { JobState, NodeState, OutputStatus } from "../types/api";
import { JOB_STATE_LABELS, NODE_STATE_LABELS, OUTPUT_STATUS_LABELS } from "../utils/format";

export function JobStateBadge({ state, raw }: { state: JobState; raw?: string | null }) {
  return (
    <span className={`badge job-${state.toLowerCase()}`} title={raw ? `HTCondor status: ${raw}` : undefined}>
      {JOB_STATE_LABELS[state]}
    </span>
  );
}

export function OutputBadge({ status }: { status: OutputStatus }) {
  return <span className={`badge output-${status.toLowerCase()}`}>{OUTPUT_STATUS_LABELS[status]}</span>;
}

export function NodeStateBadge({ state }: { state: NodeState }) {
  return <span className={`badge node-${state.toLowerCase()}`}>{NODE_STATE_LABELS[state]}</span>;
}
