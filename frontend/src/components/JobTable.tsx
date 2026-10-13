import type { PollState } from "../hooks/usePolling";
import type { JobFilter, JobList } from "../types/api";
import { formatDuration, formatTimestamp } from "../utils/format";
import { JobStateBadge, OutputBadge } from "./Badges";

const FILTERS: { value: JobFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "queued", label: "Queued" },
  { value: "running", label: "Running" },
  { value: "completed", label: "Completed" },
  { value: "failed", label: "Failed or held" },
];

interface Props {
  filter: JobFilter;
  onFilterChange: (filter: JobFilter) => void;
  poll: PollState<JobList>;
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
}

export function JobTable({ filter, onFilterChange, poll, selectedJobId, onSelect }: Props) {
  const jobs = poll.data?.jobs ?? [];
  let body;
  if (poll.loading && !poll.data) {
    body = <p className="empty">Loading jobs…</p>;
  } else if (!poll.data) {
    body = <p className="empty">Job list unavailable.</p>;
  } else if (jobs.length === 0) {
    body = <p className="empty">No jobs match this filter.</p>;
  } else {
    body = (
      <div className="table-wrap">
        <table className="jobs">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Owner</th>
              <th>Status</th>
              <th>Submitted</th>
              <th>Compute node</th>
              <th>Runtime</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr
                key={job.id}
                className={job.id === selectedJobId ? "selected" : undefined}
                tabIndex={0}
                aria-selected={job.id === selectedJobId}
                onClick={() => onSelect(job.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(job.id);
                  }
                }}
              >
                <td className="mono">{job.id}</td>
                <td>{job.owner ?? "—"}</td>
                <td>
                  <JobStateBadge state={job.state} raw={job.raw_status} />
                </td>
                <td>{formatTimestamp(job.submitted_at)}</td>
                <td className="mono">{job.node ?? "—"}</td>
                <td>{formatDuration(job.runtime_seconds)}</td>
                <td>
                  <OutputBadge status={job.output_status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Jobs</h2>
        <div className="filters" role="tablist" aria-label="Job status filter">
          {FILTERS.map((item) => (
            <button
              key={item.value}
              role="tab"
              aria-selected={filter === item.value}
              className={filter === item.value ? "active" : undefined}
              onClick={() => onFilterChange(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      {body}
    </section>
  );
}
