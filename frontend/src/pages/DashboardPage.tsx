import { useState } from "react";
import { JobDetailPanel } from "../components/JobDetailPanel";
import { JobTable } from "../components/JobTable";
import { MonitoringBanner, RefreshStatus } from "../components/MonitoringStatus";
import { NodeGrid } from "../components/NodeGrid";
import { RecentActivity } from "../components/RecentActivity";
import { SummaryCards } from "../components/SummaryCards";
import { usePolling } from "../hooks/usePolling";
import { api } from "../services/api";
import type { JobFilter } from "../types/api";

export function DashboardPage() {
  const [filter, setFilter] = useState<JobFilter>("all");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const summary = usePolling(api.summary, "summary");
  const jobs = usePolling((signal) => api.jobs(filter, signal), `jobs:${filter}`);
  const nodes = usePolling(api.nodes, "nodes");

  const polls = [summary, jobs, nodes];
  const error = polls.find((poll) => poll.error)?.error ?? null;
  // Report the oldest refresh so the timestamp never overstates freshness.
  const times = polls.flatMap((poll) => (poll.lastSuccess ? [poll.lastSuccess.getTime()] : []));
  const lastSuccess = times.length === polls.length ? new Date(Math.min(...times)) : null;

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>HTCondor Job Lifecycle</h1>
          <p className="muted">Submission → queue → match → execution → completion → output return</p>
        </div>
        <RefreshStatus lastSuccess={lastSuccess} error={error} />
      </header>
      <MonitoringBanner error={error} lastSuccess={lastSuccess} />
      <SummaryCards summary={summary.data} />
      <div className="layout">
        <div className="column">
          <JobTable
            filter={filter}
            onFilterChange={setFilter}
            poll={jobs}
            selectedJobId={selectedJobId}
            onSelect={setSelectedJobId}
          />
          <NodeGrid nodes={nodes.data?.nodes ?? null} loading={nodes.loading} onSelectJob={setSelectedJobId} />
        </div>
        <aside className="column">
          {selectedJobId ? (
            <JobDetailPanel key={selectedJobId} jobId={selectedJobId} onClose={() => setSelectedJobId(null)} />
          ) : (
            <section className="panel">
              <p className="empty">Select a job to follow its lifecycle.</p>
            </section>
          )}
          <RecentActivity summary={summary.data} onSelectJob={setSelectedJobId} />
        </aside>
      </div>
    </div>
  );
}
