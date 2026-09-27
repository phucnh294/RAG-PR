import { useCallback, useEffect, useState } from "react";
import {
  fetchAgentDefaults,
  fetchAgentRun,
  fetchAgentRuns,
  startAgentRun,
  type AgentCaseRunResult,
  type AgentDefaults,
  type AgentRunDetail,
  type AgentRunSummary,
  type ArtifactRef,
} from "../api/client";
import AgentReport, { ArtifactImage, ExecutionEvidence } from "../components/AgentReport";
import AgentStepCard, { CANONICAL_STEPS, splitRound } from "../components/AgentStepCard";

const POLL_INTERVAL_MS = 2000;
const ACTIVE = new Set(["queued", "running"]);

interface AgentsPageProps {
  /** Polling only runs while this tab is shown. */
  active: boolean;
}

/** Steps in the order they ran (including revision rounds), followed by the canonical
 * steps that haven't started yet, so a running pipeline shows what is still to come. */
function orderedStepNames(steps: Record<string, unknown>, finished: boolean): string[] {
  const names = Object.keys(steps);
  if (finished) return names;
  const started = new Set(names.map((name) => splitRound(name)[0]));
  return [...names, ...CANONICAL_STEPS.filter((name) => !started.has(name))];
}

interface CaptureOutput {
  screenshot?: ArtifactRef;
}

interface AutomationOutput {
  spec_ts?: ArtifactRef | null;
  results?: AgentCaseRunResult[];
}

export default function AgentsPage({ active }: AgentsPageProps) {
  const [defaults, setDefaults] = useState<AgentDefaults | null>(null);
  const [targetUrl, setTargetUrl] = useState("");
  const [requirement, setRequirement] = useState("");
  const [runs, setRuns] = useState<AgentRunSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AgentRunDetail | null>(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshRuns = useCallback(() => {
    fetchAgentRuns()
      .then((loaded) => {
        setRuns(loaded);
        setSelectedId((current) => current ?? loaded[0]?.run_id ?? null);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load runs"));
  }, []);

  const refreshDetail = useCallback((runId: string) => {
    fetchAgentRun(runId)
      .then(setDetail)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load run"));
  }, []);

  useEffect(() => {
    fetchAgentDefaults()
      .then((loaded) => {
        setDefaults(loaded);
        setTargetUrl(loaded.target_url);
        setRequirement(loaded.requirement);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load defaults"));
  }, []);

  useEffect(() => {
    if (active) refreshRuns();
  }, [active, refreshRuns]);

  useEffect(() => {
    if (selectedId) refreshDetail(selectedId);
    else setDetail(null);
  }, [selectedId, refreshDetail]);

  const running = detail !== null && ACTIVE.has(detail.status);
  const detailStatus = detail?.status;
  useEffect(() => {
    // The final poll may fetch the list a moment before the run's last write; refresh
    // once more when the run settles so "A run is in progress" clears.
    if (detailStatus && !ACTIVE.has(detailStatus)) refreshRuns();
  }, [detailStatus, refreshRuns]);
  useEffect(() => {
    if (!active || !running || !selectedId) return;
    const timer = window.setInterval(() => {
      refreshDetail(selectedId);
      refreshRuns();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [active, running, selectedId, refreshDetail, refreshRuns]);

  async function run() {
    setStarting(true);
    setError(null);
    try {
      const started = await startAgentRun(targetUrl, requirement);
      setSelectedId(started.run_id);
      refreshRuns();
      refreshDetail(started.run_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start run");
    } finally {
      setStarting(false);
    }
  }

  const record = detail?.record;
  const capture = record?.steps.step1_capture?.output as CaptureOutput | undefined;
  const automation = record?.steps.step6_test_automation?.output as AutomationOutput | undefined;
  const anyActive = runs.some((item) => ACTIVE.has(item.status));

  return (
    <section className="page agents-page">
      <h2>Agents</h2>
      <p className="agent-muted">
        UI analysis → business rules → test design → business confirmation → Playwright
        automation → test validation. Every step shows the exact input it received, the output it
        returned, each LLM call, and the contract checks run on that output.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="agents-layout">
        <aside className="agents-side">
          <div className="agent-form">
            <label>
              Target page
              <input value={targetUrl} onChange={(event) => setTargetUrl(event.target.value)} />
            </label>
            {defaults && (
              <p className="agent-muted">
                Allowed hosts: {defaults.allowed_target_hosts.join(", ")}. Open the page yourself
                at <a href="http://localhost:8080/myweb/">localhost:8080/myweb</a>.
              </p>
            )}
            <label>
              Requirement (input of the business agent)
              <textarea
                rows={12}
                value={requirement}
                onChange={(event) => setRequirement(event.target.value)}
              />
            </label>
            {defaults && (
              <p className="agent-muted">
                Vision: {defaults.models.vision?.model} · Text: {defaults.models.text?.model} · up
                to {defaults.max_design_rounds} design rounds
              </p>
            )}
            <div className="agent-form-actions">
              <button
                className="primary"
                onClick={run}
                disabled={starting || anyActive || !targetUrl || !requirement.trim()}
              >
                {anyActive ? "A run is in progress…" : starting ? "Starting…" : "Run agents"}
              </button>
              {defaults && requirement !== defaults.requirement && (
                <button onClick={() => setRequirement(defaults.requirement)}>
                  Reset requirement
                </button>
              )}
            </div>
          </div>

          <div className="agents-runs-header">
            <h3>Runs</h3>
            <button onClick={refreshRuns}>Refresh</button>
          </div>
          <ul className="logs-list agents-runs">
            {runs.length === 0 && <li className="empty-hint">No runs yet.</li>}
            {runs.map((item) => (
              <li
                key={item.run_id}
                className={item.run_id === selectedId ? "active" : ""}
                onClick={() => setSelectedId(item.run_id)}
              >
                <div className="log-entry-header">
                  <span className={`agent-step-status ${item.status}`}>{item.status}</span>
                  {item.total !== null && (
                    <span className="log-user">
                      {item.passed}/{item.total} passed
                    </span>
                  )}
                  <span className="log-time">{new Date(item.created_at).toLocaleString()}</span>
                </div>
                <p className="log-summary">
                  {item.current_step ? `at ${item.current_step}` : item.target_url}
                  {item.username ? ` · ${item.username}` : ""}
                </p>
              </li>
            ))}
          </ul>
        </aside>

        <div className="agents-detail">
          {!record ? (
            <p className="empty-hint">Start a run or select one to see every agent step.</p>
          ) : (
            <>
              <div className="agent-run-header">
                <span className={`agent-step-status ${record.status}`}>{record.status}</span>
                <code>{record.run_id}</code>
                {record.log_file_stem && (
                  <span className="agent-muted" title="Run folder: README.md, agents/, test-cases/">
                    folder: pipeline-logs/agents/{record.log_file_stem}/
                  </span>
                )}
                <span className="agent-muted">
                  {record.target_url} · vision {record.models.vision?.model} · text{" "}
                  {record.models.text?.model}
                </span>
              </div>
              {record.error && <p className="error">{record.error}</p>}
              {record.design_rounds && record.design_rounds.length > 1 && (
                <p className="agent-muted">
                  Design rounds:{" "}
                  {record.design_rounds
                    .map(
                      (round) =>
                        `#${round.round} ${round.approved.length} approved / ${round.rejected.length} rejected`,
                    )
                    .join(" → ")}
                </p>
              )}
              {capture?.screenshot && (
                <details className="agent-capture">
                  <summary>Captured page (what the UI analysis agent saw)</summary>
                  <ArtifactImage
                    runId={record.run_id}
                    artifact={capture.screenshot}
                    alt="Captured page"
                  />
                </details>
              )}
              <div className="agent-steps">
                {orderedStepNames(record.steps, !ACTIVE.has(record.status)).map((name) => (
                  <AgentStepCard
                    key={name}
                    runId={record.run_id}
                    name={name}
                    step={record.steps[name] ?? null}
                    isCurrent={record.current_step === name}
                  />
                ))}
              </div>
              {(automation?.results?.length ?? 0) > 0 && (
                <ExecutionEvidence
                  runId={record.run_id}
                  caseResults={automation?.results ?? []}
                  testCases={record.test_cases ?? []}
                />
              )}
              {record.report && (
                <AgentReport
                  runId={record.run_id}
                  report={record.report}
                  spec={automation?.spec_ts ?? null}
                />
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
