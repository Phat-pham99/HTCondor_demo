import type { ApiError } from "../services/api";
import { formatTimestamp } from "../utils/format";

const MESSAGES: Record<ApiError["kind"], string> = {
  backend_unreachable: "The dashboard backend cannot be reached.",
  htcondor_unavailable: "The backend is running but cannot query the HTCondor pool.",
  not_found: "Requested data was not found.",
  http: "The backend returned an unexpected error.",
};

export function RefreshStatus({ lastSuccess, error }: { lastSuccess: Date | null; error: ApiError | null }) {
  const tone = error ? "stale" : lastSuccess ? "live" : "pending";
  return (
    <div className={`refresh refresh-${tone}`} role="status">
      <span className="dot" aria-hidden="true" />
      {lastSuccess ? `Last successful refresh ${formatTimestamp(lastSuccess)}` : "Waiting for first refresh…"}
    </div>
  );
}

export function MonitoringBanner({ error, lastSuccess }: { error: ApiError | null; lastSuccess: Date | null }) {
  if (!error) return null;
  return (
    <div className="monitoring-banner" role="alert">
      <strong>Monitoring unavailable.</strong> {MESSAGES[error.kind]}{" "}
      {lastSuccess
        ? `Showing data from ${formatTimestamp(lastSuccess)}; it may be out of date.`
        : "No data has been loaded yet."}{" "}
      This is a monitoring problem, not a job failure.
    </div>
  );
}
