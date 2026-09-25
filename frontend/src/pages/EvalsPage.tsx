import { useState } from "react";
import { runGuardrailEval, type CategoryMetrics, type EvalReport } from "../api/client";

const CATEGORY_LABELS: Record<string, string> = {
  real: "Real (legitimate, answerable)",
  expect: "Expect (legitimate, out-of-scope)",
  attack: "Attack (adversarial / injection)",
};

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function formatScore(value: number | null): string {
  return value === null ? "—" : value.toFixed(2);
}

function MetricCard({ metrics }: { metrics: CategoryMetrics }) {
  const falseBlockRate = metrics.false_block_rate;
  const hasFalseBlocks = falseBlockRate !== null && falseBlockRate > 0;

  return (
    <div className="eval-metric-card">
      <h3>{CATEGORY_LABELS[metrics.category] ?? metrics.category}</h3>
      <p className="eval-metric-count">{metrics.query_count} queries</p>
      <dl className="eval-metric-list">
        {metrics.recall_at_k !== null && (
          <>
            <dt>Recall@k</dt>
            <dd>{formatPercent(metrics.recall_at_k)}</dd>
          </>
        )}
        {metrics.mrr !== null && (
          <>
            <dt>MRR</dt>
            <dd>{formatScore(metrics.mrr)}</dd>
          </>
        )}
        {metrics.refusal_rate !== null && (
          <>
            <dt>Refusal rate</dt>
            <dd>{formatPercent(metrics.refusal_rate)}</dd>
          </>
        )}
        {metrics.block_rate !== null && (
          <>
            <dt>Block rate</dt>
            <dd>{formatPercent(metrics.block_rate)}</dd>
          </>
        )}
        {falseBlockRate !== null && (
          <>
            <dt>False block rate</dt>
            <dd className={hasFalseBlocks ? "eval-metric-warn" : "eval-metric-ok"}>
              {formatPercent(falseBlockRate)}
            </dd>
          </>
        )}
      </dl>
    </div>
  );
}

export default function EvalsPage() {
  const [report, setReport] = useState<EvalReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const result = await runGuardrailEval();
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run evaluation");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="page evals-page">
      <div className="evals-toolbar">
        <h2>Guardrail Evaluation</h2>
        <button onClick={handleRun} disabled={loading}>
          {loading ? "Running…" : "Run Evaluation"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {!report && !loading && !error && (
        <p className="empty-hint">
          Run the golden set against the live guardrail judge and answer model to see
          recall/MRR, refusal rate, and block rate.
        </p>
      )}
      {report && (
        <>
          <p className="eval-generated-at">
            Generated {new Date(report.generated_at).toLocaleString()} (k={report.k})
          </p>
          <div className="eval-metrics">
            {report.categories.map((metrics) => (
              <MetricCard key={metrics.category} metrics={metrics} />
            ))}
          </div>
          <div className="table-scroll">
            <table className="eval-results">
              <thead>
                <tr>
                  <th>Category</th>
                  <th>Query</th>
                  <th>Blocked</th>
                  <th>Matched rank</th>
                  <th>Refused</th>
                  <th>Answer excerpt</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map((result, index) => (
                  <tr key={index}>
                    <td>{result.category}</td>
                    <td>{result.query}</td>
                    <td>{result.blocked ? "yes" : "no"}</td>
                    <td>{result.matched_rank ?? "—"}</td>
                    <td>{result.refused === null ? "—" : result.refused ? "yes" : "no"}</td>
                    <td>{result.answer_excerpt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
