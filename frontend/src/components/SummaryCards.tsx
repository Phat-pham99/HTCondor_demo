import type { ClusterSummary } from "../types/api";

interface Card {
  label: string;
  value: number | string;
  tone: string;
  hint?: string;
}

export function SummaryCards({ summary }: { summary: ClusterSummary | null }) {
  const cards: Card[] = summary
    ? [
        { label: "Queued", value: summary.jobs.idle, tone: "idle", hint: "Waiting for a compute node" },
        {
          label: "Running",
          value: summary.jobs.running + summary.jobs.transferring_output,
          tone: "running",
          hint: summary.jobs.transferring_output
            ? `${summary.jobs.transferring_output} returning output`
            : "Executing on compute nodes",
        },
        { label: "Completed", value: summary.jobs.completed, tone: "completed", hint: "Exit code 0" },
        {
          label: "Failed / held",
          value: summary.jobs.failed + summary.jobs.held,
          tone: "failed",
          hint: `${summary.jobs.failed} failed · ${summary.jobs.held} held`,
        },
        {
          label: "Compute nodes",
          value: summary.nodes.total,
          tone: "nodes",
          hint:
            `${summary.nodes.busy} busy · ${summary.nodes.available} available` +
            (summary.nodes.offline ? ` · ${summary.nodes.offline} offline` : ""),
        },
      ]
    : ["Queued", "Running", "Completed", "Failed / held", "Compute nodes"].map((label) => ({
        label,
        value: "…",
        tone: "loading",
      }));

  return (
    <section className="cards" aria-label="Cluster overview">
      {cards.map((card) => (
        <div key={card.label} className={`card card-${card.tone}`}>
          <div className="card-label">{card.label}</div>
          <div className="card-value">{card.value}</div>
          {card.hint && <div className="card-hint">{card.hint}</div>}
        </div>
      ))}
    </section>
  );
}
