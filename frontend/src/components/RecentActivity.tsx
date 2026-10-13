import type { ClusterSummary } from "../types/api";
import { formatTimestamp } from "../utils/format";

interface Props {
  summary: ClusterSummary | null;
  onSelectJob: (jobId: string) => void;
}

export function RecentActivity({ summary, onSelectJob }: Props) {
  let body;
  if (!summary) {
    body = <p className="empty">Loading activity…</p>;
  } else if (!summary.event_log_available) {
    body = <p className="empty">The HTCondor event log is not available to the dashboard.</p>;
  } else if (summary.recent_activity.length === 0) {
    body = <p className="empty">No job events recorded yet.</p>;
  } else {
    body = (
      <ul className="activity">
        {summary.recent_activity.map((item, index) => (
          <li key={`${item.job_id}-${item.timestamp}-${index}`}>
            <span className="time">{formatTimestamp(item.timestamp)}</span>
            <button className="link mono" onClick={() => onSelectJob(item.job_id)}>
              {item.job_id}
            </button>
            <span>{item.title}</span>
            {item.host && <span className="muted mono">{item.host}</span>}
          </li>
        ))}
      </ul>
    );
  }
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Recent activity</h2>
      </div>
      {body}
    </section>
  );
}
