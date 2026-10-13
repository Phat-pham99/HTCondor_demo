import { usePolling, type PollState } from "../hooks/usePolling";
import { api } from "../services/api";
import type { JobDetail, JobEvents, JobOutput, LifecycleStep, StepStatus } from "../types/api";
import { FAILURE_STAGE_LABELS, formatBytes, formatDuration, formatMemory, formatTimestamp } from "../utils/format";
import { JobStateBadge, OutputBadge } from "./Badges";

const STEP_ICONS: Record<StepStatus, string> = { DONE: "✓", CURRENT: "●", PENDING: "○", FAILED: "✕", SKIPPED: "–" };

interface Props {
  jobId: string;
  onClose: () => void;
}

export function JobDetailPanel({ jobId, onClose }: Props) {
  const job = usePolling((signal) => api.job(jobId, signal), `job:${jobId}`);
  const events = usePolling((signal) => api.events(jobId, signal), `events:${jobId}`);
  const output = usePolling((signal) => api.output(jobId, signal), `output:${jobId}`);
  const detail = job.data;

  let body;
  if (job.loading && !detail) {
    body = <p className="empty">Loading job {jobId}…</p>;
  } else if (!detail && job.error?.kind === "not_found") {
    body = <p className="empty">Job {jobId} is not in the queue or the retained history.</p>;
  } else if (!detail) {
    body = <p className="empty">Job details unavailable. {job.error?.message}</p>;
  } else {
    body = (
      <>
        <Overview job={detail} />
        <Failure job={detail} />
        <Timeline steps={detail.lifecycle} />
        <EventList poll={events} />
        <OutputSection poll={output} />
        <details className="raw">
          <summary>Raw HTCondor attributes</summary>
          <pre>{JSON.stringify(detail.raw, null, 2)}</pre>
        </details>
      </>
    );
  }

  return (
    <section className="panel detail" aria-label={`Job ${jobId}`}>
      <div className="panel-header">
        <h2>
          Job <span className="mono">{jobId}</span>
        </h2>
        {detail && <JobStateBadge state={detail.state} raw={detail.raw_status} />}
        <button className="close" onClick={onClose} aria-label="Close job details">
          ×
        </button>
      </div>
      {body}
    </section>
  );
}

function exitText(job: JobDetail): string {
  if (job.exit_by_signal) return `Killed by signal ${job.exit_signal ?? "?"}`;
  return job.exit_code === null ? "—" : String(job.exit_code);
}

function Overview({ job }: { job: JobDetail }) {
  const command = [job.command, job.arguments].filter(Boolean).join(" ");
  return (
    <>
      <p className="stage">
        <strong>Now:</strong> {job.current_stage}
      </p>
      <dl className="facts">
        <dt>Compute node</dt>
        <dd className="mono">{job.node ?? "Not assigned"}</dd>
        {job.slot && (
          <>
            <dt>Slot</dt>
            <dd className="mono">{job.slot}</dd>
          </>
        )}
        <dt>Owner</dt>
        <dd>{job.owner ?? "—"}</dd>
        <dt>Submitted</dt>
        <dd>{formatTimestamp(job.submitted_at)}</dd>
        <dt>Waited in queue</dt>
        <dd>{formatDuration(job.queue_wait_seconds)}</dd>
        <dt>Ran for</dt>
        <dd>{formatDuration(job.runtime_seconds)}</dd>
        <dt>Exit code</dt>
        <dd>{exitText(job)}</dd>
        <dt>Output</dt>
        <dd>
          <OutputBadge status={job.output_status} />
        </dd>
        <dt>Requested</dt>
        <dd>
          {job.request_cpus ?? "?"} CPU · {formatMemory(job.request_memory_mb)}
        </dd>
        <dt>Command</dt>
        <dd className="mono">{command || "—"}</dd>
        <dt>Source</dt>
        <dd>
          {job.source === "queue" ? "Active queue" : "Job history"}
          {job.job_starts ? ` · started ${job.job_starts}×` : ""}
        </dd>
      </dl>
    </>
  );
}

function Failure({ job }: { job: JobDetail }) {
  const reason = job.failure_reason ?? job.hold_reason;
  if (!job.failure_stage && !reason) return null;
  return (
    <div className="failure" role="note">
      <strong>
        {job.state === "HELD" ? "Job held" : "Job failed"}
        {job.failure_stage ? ` at stage: ${FAILURE_STAGE_LABELS[job.failure_stage]}` : ""}
      </strong>
      {reason && <p>{reason}</p>}
      {job.hold_reason_code !== null && <p className="muted mono">HoldReasonCode {job.hold_reason_code}</p>}
    </div>
  );
}

function Timeline({ steps }: { steps: LifecycleStep[] }) {
  return (
    <div className="section">
      <h3>Lifecycle</h3>
      <ol className="timeline">
        {steps.map((step) => (
          <li key={step.key} className={`step step-${step.status.toLowerCase()}`}>
            <span className="step-icon" aria-label={step.status.toLowerCase()}>
              {STEP_ICONS[step.status]}
            </span>
            <span className="step-time">{formatTimestamp(step.timestamp)}</span>
            <span className="step-label">{step.label}</span>
            {step.detail && <span className="step-detail">{step.detail}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function EventList({ poll }: { poll: PollState<JobEvents> }) {
  const data = poll.data;
  let body;
  if (!data) {
    body = <p className="empty">{poll.loading ? "Loading events…" : "Events unavailable."}</p>;
  } else if (data.events.length === 0) {
    body = <p className="empty">No events recorded.</p>;
  } else {
    body = (
      <ul className="events">
        {data.events.map((event) => (
          <li key={event.sequence}>
            <span className="time">{formatTimestamp(event.timestamp)}</span>
            <span>
              {event.title}
              {event.host && <span className="muted mono"> · {event.host}</span>}
              {event.detail && <span className="muted"> — {event.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <div className="section">
      <h3>Event log</h3>
      {data && !data.event_log_available && (
        <p className="muted">Event log unavailable; times are derived from the job ClassAd.</p>
      )}
      {body}
    </div>
  );
}

function fileStatus(file: JobOutput["files"][number]): string {
  if (file.exists === false) return "missing";
  if (file.exists === null) return "not checked";
  return `${formatBytes(file.size_bytes)} · ${formatTimestamp(file.modified_at)}`;
}

function OutputSection({ poll }: { poll: PollState<JobOutput> }) {
  const data = poll.data;
  let body;
  if (!data) {
    body = <p className="empty">{poll.loading ? "Loading output…" : "Output information unavailable."}</p>;
  } else if (data.files.length === 0) {
    body = <p className="empty">This job declares no output files.</p>;
  } else {
    body = data.files.map((file) => (
      <div key={`${file.role}:${file.path}`} className="output-file">
        <div className="output-head">
          <span className="role">{file.role}</span>
          <span className="mono">{file.name}</span>
          <span className="muted">{fileStatus(file)}</span>
        </div>
        {file.note && <p className="muted">{file.note}</p>}
        {file.preview !== null &&
          (file.preview ? (
            <pre className="preview">
              {file.preview}
              {file.truncated ? "\n… (truncated)" : ""}
            </pre>
          ) : (
            <p className="muted">(empty file)</p>
          ))}
      </div>
    ));
  }
  return (
    <div className="section">
      <div className="section-head">
        <h3>Output</h3>
        {data && <OutputBadge status={data.status} />}
      </div>
      {body}
    </div>
  );
}
