import { useCallback, useEffect, useState } from "react";
import {
  fetchLogDetail,
  fetchLogs,
  type LogDetail,
  type LogSummary,
  type PipelineName,
} from "../api/client";

type PipelineFilter = "all" | PipelineName;

const FILTERS: PipelineFilter[] = ["all", "retrieval", "indexing"];

export default function LogsPage() {
  const [filter, setFilter] = useState<PipelineFilter>("all");
  const [logs, setLogs] = useState<LogSummary[]>([]);
  const [selected, setSelected] = useState<LogSummary | null>(null);
  const [detail, setDetail] = useState<LogDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchLogs(filter === "all" ? undefined : filter)
      .then((result) => {
        setLogs(result);
        setError(null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load logs"));
  }, [filter]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    fetchLogDetail(selected.pipeline, selected.id)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load log"));
  }, [selected]);

  return (
    <section className="page logs-page">
      <h2>Pipeline Logs</h2>
      <div className="logs-toolbar">
        <div className="logs-filter">
          {FILTERS.map((option) => (
            <button
              key={option}
              className={filter === option ? "active" : ""}
              onClick={() => setFilter(option)}
            >
              {option}
            </button>
          ))}
        </div>
        <button onClick={refresh}>Refresh</button>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="logs-layout">
        <ul className="logs-list">
          {logs.length === 0 && <li className="empty-hint">No pipeline runs logged yet.</li>}
          {logs.map((log) => (
            <li
              key={`${log.pipeline}-${log.id}`}
              className={selected?.id === log.id ? "active" : ""}
              onClick={() => setSelected(log)}
            >
              <div className="log-entry-header">
                <span className={`pipeline-badge ${log.pipeline}`}>{log.pipeline}</span>
                <span className="log-time">{log.created_at}</span>
              </div>
              <p className="log-summary">{log.summary || "(empty)"}</p>
            </li>
          ))}
        </ul>
        <div className="log-detail">
          {detail ? (
            <pre>{JSON.stringify(detail.record, null, 2)}</pre>
          ) : (
            <p className="empty-hint">Select a log entry to view the full record.</p>
          )}
        </div>
      </div>
    </section>
  );
}
