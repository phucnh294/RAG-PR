import { useState } from "react";
import {
  runRerankComparison,
  type RankingMetrics,
  type RerankComparisonReport,
  type RerankQueryResult,
} from "../api/client";

type MetricKey = Exclude<keyof RankingMetrics, "query_count">;

const METRIC_ROWS: { key: MetricKey; label: (k: number) => string; percent: boolean }[] = [
  { key: "recall_at_1", label: () => "Recall@1", percent: true },
  { key: "recall_at_k", label: (k) => `Recall@${k}`, percent: true },
  { key: "mrr", label: () => "MRR", percent: false },
  { key: "ndcg_at_k", label: (k) => `nDCG@${k}`, percent: false },
];

function formatValue(value: number, percent: boolean): string {
  return percent ? `${Math.round(value * 100)}%` : value.toFixed(3);
}

function formatDelta(value: number, percent: boolean): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  const magnitude = Math.abs(value);
  return percent ? `${sign}${Math.round(magnitude * 100)} pts` : `${sign}${magnitude.toFixed(3)}`;
}

function deltaClass(value: number): string {
  // Ignore float noise so an unchanged metric doesn't render as a win or a loss.
  if (value > 1e-9) return "eval-metric-ok";
  if (value < -1e-9) return "eval-metric-warn";
  return "eval-metric-neutral";
}

function rankLabel(rank: number | null): string {
  return rank === null ? "miss" : `#${rank}`;
}

function movement(result: RerankQueryResult): { text: string; className: string } {
  const before = result.rank_before ?? Infinity;
  const after = result.rank_after ?? Infinity;
  if (after < before) return { text: "improved", className: "eval-metric-ok" };
  if (after > before) return { text: "worsened", className: "eval-metric-warn" };
  return { text: "same", className: "eval-metric-neutral" };
}

function formatMs(value: number | null): string {
  return value === null ? "—" : `${Math.round(value)} ms`;
}

export default function RerankComparison() {
  const [report, setReport] = useState<RerankComparisonReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      setReport(await runRerankComparison());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run rerank comparison");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="eval-section">
      <div className="evals-toolbar">
        <h2>Rerank Comparison</h2>
        <button onClick={handleRun} disabled={loading}>
          {loading ? "Running…" : "Run Comparison"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {!report && !loading && !error && (
        <p className="empty-hint">
          Ranks the same hybrid-search candidates twice (hybrid order vs. cross-encoder order)
          for every answerable golden-set query and compares recall, MRR and nDCG. Retrieval
          only, so no LLM calls are made.
        </p>
      )}
      {report && (
        <>
          <p className="eval-generated-at">
            Generated {new Date(report.generated_at).toLocaleString()} · {report.model} ·{" "}
            {report.search_mode} search · top {report.k} of {report.candidate_k} candidates
          </p>
          <div className="rerank-summary">
            <span>
              <strong>{report.baseline.query_count}</strong> queries scored
            </span>
            <span className="eval-metric-ok">{report.improved_count} improved</span>
            <span className="eval-metric-warn">{report.worsened_count} worsened</span>
            <span>{report.unchanged_count} unchanged</span>
            <span>
              Candidate-pool recall <strong>{Math.round(report.pool_recall * 100)}%</strong>
            </span>
            <span>
              Rerank latency mean <strong>{formatMs(report.mean_rerank_ms)}</strong>, p95{" "}
              <strong>{formatMs(report.p95_rerank_ms)}</strong>
            </span>
            {report.rerank_failed_count > 0 && (
              <span className="eval-metric-warn">
                {report.rerank_failed_count} rerank call(s) failed (hybrid order kept)
              </span>
            )}
          </div>
          <div className="table-scroll">
            <table className="eval-results">
              <thead>
                <tr>
                  <th>Metric</th>
                  <th className="numeric">Hybrid</th>
                  <th className="numeric">Hybrid + rerank</th>
                  <th className="numeric">Δ</th>
                </tr>
              </thead>
              <tbody>
                {METRIC_ROWS.map(({ key, label, percent }) => (
                  <tr key={key}>
                    <td>{label(report.k)}</td>
                    <td className="numeric">{formatValue(report.baseline[key], percent)}</td>
                    <td className="numeric">{formatValue(report.reranked[key], percent)}</td>
                    <td className={`numeric ${deltaClass(report.delta[key])}`}>
                      {formatDelta(report.delta[key], percent)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-scroll">
            <table className="eval-results">
              <thead>
                <tr>
                  <th>Query</th>
                  <th>Expected</th>
                  <th className="numeric">Before</th>
                  <th className="numeric">After</th>
                  <th className="numeric">In pool</th>
                  <th>Change</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map((result, index) => {
                  const change = movement(result);
                  return (
                    <tr key={index}>
                      <td>{result.query}</td>
                      <td>
                        {result.expected_document_filename}
                        {result.expected_excerpt && <div className="score">“{result.expected_excerpt}”</div>}
                      </td>
                      <td className="numeric">{rankLabel(result.rank_before)}</td>
                      <td className="numeric">{rankLabel(result.rank_after)}</td>
                      <td className="numeric">{rankLabel(result.rank_in_pool)}</td>
                      <td className={change.className}>{change.text}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {report.skipped_queries.length > 0 && (
            <details className="citation-list">
              <summary>
                {report.skipped_queries.length} skipped (expected document not indexed or query
                failed)
              </summary>
              <ul>
                {report.skipped_queries.map((query) => (
                  <li key={query}>{query}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
