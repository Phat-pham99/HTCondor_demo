import type { ComputeNode } from "../types/api";
import { formatMemory, formatTimestamp } from "../utils/format";
import { NodeStateBadge } from "./Badges";

interface Props {
  nodes: ComputeNode[] | null;
  loading: boolean;
  onSelectJob: (jobId: string) => void;
}

export function NodeGrid({ nodes, loading, onSelectJob }: Props) {
  let body;
  if (loading && !nodes) {
    body = <p className="empty">Loading compute nodes…</p>;
  } else if (!nodes) {
    body = <p className="empty">Compute-node information unavailable.</p>;
  } else if (nodes.length === 0) {
    body = <p className="empty">No compute nodes are advertising to the collector.</p>;
  } else {
    body = (
      <div className="node-grid">
        {nodes.map((node) => (
          <article key={node.name} className={`node node-card-${node.state.toLowerCase()}`}>
            <header>
              <h3 className="mono">{node.name}</h3>
              <NodeStateBadge state={node.state} />
            </header>
            <dl>
              <dt>Running job</dt>
              <dd>
                {node.running_jobs.length === 0
                  ? "—"
                  : node.running_jobs.map((jobId) => (
                      <button key={jobId} className="link mono" onClick={() => onSelectJob(jobId)}>
                        {jobId}
                      </button>
                    ))}
              </dd>
              <dt>CPU allocated</dt>
              <dd>
                {node.state === "OFFLINE" ? "—" : `${node.cpus_allocated} / ${node.cpus_total ?? "?"}`}
              </dd>
              <dt>Memory allocated</dt>
              <dd>
                {node.state === "OFFLINE"
                  ? "—"
                  : `${formatMemory(node.memory_allocated_mb)} / ${formatMemory(node.memory_total_mb)}`}
              </dd>
              <dt>Jobs completed</dt>
              <dd>{node.completed_jobs}</dd>
              <dt>Last update</dt>
              <dd>{formatTimestamp(node.last_update)}</dd>
            </dl>
            {node.raw_state && <div className="raw-state mono">HTCondor: {node.raw_state}</div>}
          </article>
        ))}
      </div>
    );
  }
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Compute nodes</h2>
      </div>
      {body}
    </section>
  );
}
