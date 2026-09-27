import { useEffect, useState } from "react";
import {
  fetchAgentArtifact,
  type AgentCaseRunResult,
  type AgentReport as Report,
  type AgentTestCaseSummary,
  type ArtifactRef,
} from "../api/client";
import RunFileLink from "./RunFileLink";

function useArtifactUrl(runId: string, name: string | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!name) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchAgentArtifact(runId, name)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setUrl(null));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [runId, name]);
  return url;
}

export function ArtifactImage({ runId, artifact, alt }: {
  runId: string;
  artifact: ArtifactRef | null | undefined;
  alt: string;
}) {
  const url = useArtifactUrl(runId, artifact?.name);
  if (!artifact) return null;
  return url ? (
    <a href={url} target="_blank" rel="noreferrer">
      <img className="agent-screenshot" src={url} alt={alt} />
    </a>
  ) : (
    <p className="empty-hint">Loading {artifact.name}…</p>
  );
}

function SpecFile({ runId, artifact }: { runId: string; artifact: ArtifactRef }) {
  const url = useArtifactUrl(runId, artifact.name);
  const [text, setText] = useState<string>("");
  useEffect(() => {
    if (!url) return;
    fetch(url)
      .then((response) => response.text())
      .then(setText)
      .catch(() => setText(""));
  }, [url]);
  return (
    <div>
      <div className="agent-spec-header">
        <code>{artifact.name}</code>
        {url && (
          <a href={url} download={artifact.name}>
            Download
          </a>
        )}
      </div>
      <pre className="agent-json">{text || "Loading…"}</pre>
    </div>
  );
}

/** Per-step proof for one executed case: result, what the page showed, screenshot. */
function CaseEvidence({
  runId,
  result,
  summary,
}: {
  runId: string;
  result: AgentCaseRunResult;
  summary: AgentTestCaseSummary | undefined;
}) {
  return (
    <details className="agent-case-evidence" open>
      <summary>
        <code>{result.case_id}</code>{" "}
        <span className={`check-badge ${result.status === "passed" ? "passed" : "error"}`}>
          {result.status}
        </span>{" "}
        <span className="agent-muted">
          {result.steps.filter((step) => step.evidence).length} screenshot(s) ·{" "}
          {(result.duration_ms / 1000).toFixed(1)}s
        </span>
      </summary>
      {summary && (
        <div className="agent-case-links">
          {["test-case.md", "result.json"].map((file) => (
            <RunFileLink
              key={file}
              load={() => fetchAgentArtifact(runId, `${summary.folder}/${file}`)}
              name={`${summary.folder}/${file}`}
              label={file}
            />
          ))}
          <span className="agent-muted">{summary.folder}/</span>
        </div>
      )}
      <ol className="agent-evidence-steps">
        {result.steps.map((step) => (
          <li key={step.index} className={step.status}>
            <div className="agent-evidence-caption">
              <strong>
                {step.index + 1}. {step.action}
              </strong>
              {step.value !== null && step.value !== "" && <code> "{step.value}"</code>} —{" "}
              <span className={`check-badge ${step.status === "failed" ? "error" : step.status === "passed" ? "passed" : "warning"}`}>
                {step.status}
              </span>
              {(step.page_messages ?? []).map((message) => (
                <div key={message} className="agent-page-message">
                  page shows: {message}
                </div>
              ))}
              {step.observed && <div className="agent-muted">observed: {step.observed}</div>}
              {step.error && <div className="error">{step.error}</div>}
            </div>
            {step.evidence && (
              <ArtifactImage runId={runId} artifact={step.evidence} alt={`Step ${step.index + 1}`} />
            )}
          </li>
        ))}
      </ol>
    </details>
  );
}

/** Test case results with per-step screenshots. Shown as soon as test automation has run —
 * it does not wait for the validation report (step 7). */
export function ExecutionEvidence({
  runId,
  caseResults,
  testCases,
}: {
  runId: string;
  caseResults: AgentCaseRunResult[];
  testCases: AgentTestCaseSummary[];
}) {
  const summaries = new Map(testCases.map((item) => [item.case_id, item]));
  const passed = caseResults.filter((result) => result.status === "passed").length;
  return (
    <section className="agent-report">
      <h3>
        Test case results — {passed}/{caseResults.length} passed
      </h3>
      <p className="agent-muted">
        Screenshot, message shown on the page and observed value after every executed step — the
        proof each case passed or failed.
      </p>
      {caseResults.map((result) => (
        <CaseEvidence
          key={result.case_id}
          runId={runId}
          result={result}
          summary={summaries.get(result.case_id)}
        />
      ))}
    </section>
  );
}

interface AgentReportProps {
  runId: string;
  report: Report;
  spec: ArtifactRef | null;
}

export default function AgentReport({
  runId,
  report,
  spec,
}: AgentReportProps) {
  const analysis = new Map(report.failure_analysis.map((item) => [item.case_id, item]));

  return (
    <section className="agent-report">
      <h3>Validation report</h3>
      <div className="agent-metrics">
        <div className="agent-metric">
          <span>{report.total}</span>executed
        </div>
        <div className="agent-metric passed">
          <span>{report.passed}</span>passed
        </div>
        <div className="agent-metric failed">
          <span>{report.failed + report.errored}</span>failed
        </div>
        <div className="agent-metric">
          <span>{Math.round(report.pass_rate * 100)}%</span>pass rate
        </div>
        <div className="agent-metric">
          <span>
            {report.rules_verified.length}/{Object.keys(report.rule_coverage).length}
          </span>
          rules verified
        </div>
      </div>
      {report.summary && <p className="agent-summary">{report.summary}</p>}

      <h4>Test cases</h4>
      <div className="table-scroll">
        <table className="agent-table">
          <thead>
            <tr>
              <th>Case</th>
              <th>Title</th>
              <th>Rules</th>
              <th>Result</th>
              <th>Failure</th>
            </tr>
          </thead>
          <tbody>
            {report.cases.map((item) => {
              const cause = analysis.get(item.case_id);
              return (
                <tr key={item.case_id}>
                  <td>
                    <code>{item.case_id}</code>
                  </td>
                  <td>{item.title}</td>
                  <td>{item.source_rule_ids.join(", ")}</td>
                  <td>
                    <span className={`check-badge ${item.status === "passed" ? "passed" : "error"}`}>
                      {item.status}
                    </span>
                  </td>
                  <td>
                    {item.error && (
                      <div>
                        Step {item.failed_step}: {item.error}
                      </div>
                    )}
                    {cause && (
                      <div className="agent-muted">
                        <strong>{cause.suspected_cause}</strong> — {cause.explanation}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h4>Rule coverage</h4>
      <div className="table-scroll">
        <table className="agent-table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Covered by</th>
              <th>Verified</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(report.rule_coverage).map(([rule, cases]) => (
              <tr key={rule}>
                <td>
                  <code>{rule}</code>
                </td>
                <td>{cases.length ? cases.join(", ") : <em>not covered</em>}</td>
                <td>{report.rules_verified.includes(rule) ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {report.dropped_cases.length > 0 && (
        <>
          <h4>Cases rejected by the business agent (not executed)</h4>
          <ul>
            {report.dropped_cases.map((item) => (
              <li key={item.case_id}>
                <code>{item.case_id}</code> {item.title} — {item.reason}
              </li>
            ))}
          </ul>
        </>
      )}

      {spec && (
        <>
          <h4>Generated Playwright spec</h4>
          <SpecFile runId={runId} artifact={spec} />
        </>
      )}
    </section>
  );
}
