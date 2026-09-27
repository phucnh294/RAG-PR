import {
  fetchAgentHandoff,
  type AgentCheck,
  type AgentHandoff,
  type AgentLlmCall,
  type AgentStepRecord,
} from "../api/client";
import RunFileLink from "./RunFileLink";

const STEP_LABELS: Record<string, string> = {
  step1_capture: "Page capture",
  step2_ui_analysis: "UI analysis agent",
  step3_business_rules: "Business agent — rules",
  step4_test_design: "Test design agent",
  step5_business_confirmation: "Business agent — confirm cases",
  step6_test_automation: "Test automation (Playwright)",
  step7_test_validation: "Test validation agent",
};

const STEP_ACTORS: Record<string, string> = {
  step1_capture: "test-runner",
  step2_ui_analysis: "vision model",
  step3_business_rules: "text model",
  step4_test_design: "text model",
  step5_business_confirmation: "text model",
  step6_test_automation: "test-runner",
  step7_test_validation: "code + text model",
};

export const CANONICAL_STEPS = Object.keys(STEP_LABELS);

/** "step4_test_design_r2" -> ["step4_test_design", 2]. */
export function splitRound(name: string): [string, number] {
  const match = /^(.*)_r(\d+)$/.exec(name);
  return match ? [match[1], Number(match[2])] : [name, 1];
}

export function stepLabel(name: string): string {
  const [base, round] = splitRound(name);
  const number = base.match(/^step(\d+)/)?.[1] ?? "?";
  const label = STEP_LABELS[base] ?? base;
  return `${number}. ${label}${round > 1 ? ` (round ${round})` : ""}`;
}

function Json({ value }: { value: unknown }) {
  return <pre className="agent-json">{JSON.stringify(value, null, 2)}</pre>;
}

function ChecksTable({ checks }: { checks: AgentCheck[] }) {
  return (
    <table className="agent-checks">
      <thead>
        <tr>
          <th>Check</th>
          <th>Result</th>
          <th>Detail</th>
        </tr>
      </thead>
      <tbody>
        {checks.map((check) => (
          <tr key={check.name}>
            <td>
              <code>{check.name}</code>
            </td>
            <td>
              <span
                className={`check-badge ${check.passed ? "passed" : check.severity}`}
                title={check.severity === "error" ? "Failing this stops the run" : "Logged only"}
              >
                {check.passed ? "pass" : check.severity === "error" ? "FAIL" : "warn"}
              </span>
            </td>
            <td>{check.detail}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function LlmCall({ call }: { call: AgentLlmCall }) {
  const status = call.error ? "error" : call.valid ? "valid" : "invalid";
  return (
    <details className="agent-llm-call">
      <summary>
        Attempt {call.attempt} · {call.provider}/{call.model} · schema {call.response_format} ·{" "}
        <span className={`check-badge ${status === "valid" ? "passed" : "error"}`}>{status}</span>
        {call.duration_ms !== undefined && (
          <span className="agent-muted"> · {(call.duration_ms / 1000).toFixed(1)}s</span>
        )}
      </summary>
      <h5>Messages sent</h5>
      <Json value={call.messages} />
      <h5>Raw response</h5>
      <pre className="agent-json">{call.raw_response ?? call.error ?? "(none)"}</pre>
      {Boolean(call.parse_error || call.validation_errors) && (
        <>
          <h5>Why it was rejected</h5>
          <Json value={call.parse_error ?? call.validation_errors} />
        </>
      )}
    </details>
  );
}

/** The step's input/output Markdown files and the earlier agents' files it was built from. */
function HandoffFiles({ runId, handoff }: { runId: string; handoff: AgentHandoff }) {
  const fileName = (path: string) => path.split("/").pop() ?? path;
  return (
    <section>
      <h4>Agent files</h4>
      <div className="agent-case-links">
        {(["input", "output"] as const).map((kind) => {
          const path = handoff[kind];
          return path ? (
            <RunFileLink
              key={kind}
              load={() => fetchAgentHandoff(runId, path)}
              name={path}
              label={`${kind}.md`}
            />
          ) : null;
        })}
        {handoff.output && <span className="agent-muted">{fileName(handoff.output)}</span>}
      </div>
      {handoff.sources && handoff.sources.length > 0 && (
        <p className="agent-muted">
          Input built from:{" "}
          {handoff.sources.map((source) => (
            <code key={source} title={source}>
              {fileName(source)}{" "}
            </code>
          ))}
        </p>
      )}
    </section>
  );
}

interface AgentStepCardProps {
  runId: string;
  name: string;
  step: AgentStepRecord | null;
  isCurrent: boolean;
}

export default function AgentStepCard({ runId, name, step, isCurrent }: AgentStepCardProps) {
  const status = step?.status ?? "pending";
  const checks = step?.checks ?? [];
  const failedChecks = checks.filter((check) => !check.passed);
  const [base] = splitRound(name);

  return (
    <details className={`agent-step ${status}`} open={status === "failed"}>
      <summary>
        <span className={`agent-step-status ${status}`}>
          {isCurrent && status === "running" ? "running…" : status}
        </span>
        <span className="agent-step-title">{stepLabel(name)}</span>
        <span className="agent-muted">{STEP_ACTORS[base]}</span>
        <span className="agent-step-meta">
          {checks.length > 0 &&
            (failedChecks.length === 0
              ? `${checks.length} checks passed`
              : `${failedChecks.length}/${checks.length} checks flagged`)}
          {step?.duration_ms !== undefined && ` · ${(step.duration_ms / 1000).toFixed(1)}s`}
        </span>
      </summary>
      {step === null ? (
        <p className="empty-hint">Not started yet.</p>
      ) : (
        <div className="agent-step-body">
          {step.error && <p className="error">{step.error}</p>}
          {step.handoff && <HandoffFiles runId={runId} handoff={step.handoff} />}
          <section>
            <h4>Input</h4>
            <Json value={step.input ?? null} />
          </section>
          <section>
            <h4>Output</h4>
            {step.output === undefined ? (
              <p className="empty-hint">No output yet.</p>
            ) : (
              <Json value={step.output} />
            )}
          </section>
          {checks.length > 0 && (
            <section>
              <h4>Contract checks</h4>
              <ChecksTable checks={checks} />
            </section>
          )}
          {step.llm_calls && step.llm_calls.length > 0 && (
            <section>
              <h4>LLM calls ({step.llm_calls.length})</h4>
              {step.llm_calls.map((call) => (
                <LlmCall key={call.attempt} call={call} />
              ))}
            </section>
          )}
        </div>
      )}
    </details>
  );
}
