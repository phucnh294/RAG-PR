import { authHeaders } from "../auth/identity";
import type { ChatResponsePayload } from "./streaming";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** fetch with the caller's identity header, turning error responses into readable Errors. */
async function apiFetch(input: string | URL, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(input, {
    ...init,
    headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = typeof body.detail === "string" ? body.detail : response.statusText;
    const prefix =
      response.status === 401
        ? "Not signed in"
        : response.status === 403
          ? "Permission denied"
          : `Request failed (${response.status})`;
    throw new Error(`${prefix}: ${detail}`);
  }
  return response;
}

export interface DocumentOut {
  id: string;
  filename: string;
  content_hash: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  created_at: string;
  classification: string;
  tags: string[];
  created_by: string | null;
  created_by_username: string | null;
  can_delete: boolean;
}

export interface UploadResponse {
  document: DocumentOut;
  already_exists: boolean;
}

export interface UploadOptions {
  classification?: string;
  tags?: string;
}

export async function fetchDocuments(): Promise<DocumentOut[]> {
  const response = await apiFetch(`${API_BASE}/documents`);
  return response.json();
}

export async function uploadDocument(
  file: File,
  options: UploadOptions = {},
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (options.classification) formData.append("classification", options.classification);
  if (options.tags) formData.append("tags", options.tags);
  const response = await apiFetch(`${API_BASE}/documents`, { method: "POST", body: formData });
  return response.json();
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiFetch(`${API_BASE}/documents/${documentId}`, { method: "DELETE" });
}

export interface UserOut {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
  created_at: string;
}

export interface MeOut {
  id: string;
  username: string;
  role: string;
  allowed_classifications: string[];
  is_admin: boolean;
}

export interface ClassificationsOut {
  allowed: string[];
  default: string;
  all: string[];
}

export async function fetchDemoUsers(): Promise<UserOut[]> {
  const response = await apiFetch(`${API_BASE}/auth/demo-users`);
  return response.json();
}

export async function fetchMe(): Promise<MeOut> {
  const response = await apiFetch(`${API_BASE}/auth/me`);
  return response.json();
}

export async function fetchClassifications(): Promise<ClassificationsOut> {
  const response = await apiFetch(`${API_BASE}/auth/classifications`);
  return response.json();
}

export type PipelineName = "retrieval" | "indexing" | "agents";

export interface LogSummary {
  id: string;
  pipeline: PipelineName;
  created_at: string;
  summary: string;
  username: string | null;
}

export interface LogDetail {
  id: string;
  pipeline: PipelineName;
  record: Record<string, unknown>;
}

export async function fetchLogs(pipeline?: PipelineName): Promise<LogSummary[]> {
  const url = new URL(`${API_BASE}/logs`);
  if (pipeline) {
    url.searchParams.set("pipeline", pipeline);
  }
  const response = await apiFetch(url);
  return response.json();
}

export async function fetchLogDetail(pipeline: PipelineName, id: string): Promise<LogDetail> {
  const response = await apiFetch(`${API_BASE}/logs/${pipeline}/${id}`);
  return response.json();
}

export type EvalCategory = "real" | "expect" | "attack";

export interface GuardrailVerdict {
  layer: "input" | "output";
  verdict: "safe" | "unsafe" | "judge_error";
  reason: string;
  category: string | null;
}

export interface CategoryMetrics {
  category: EvalCategory;
  query_count: number;
  recall_at_k: number | null;
  mrr: number | null;
  refusal_rate: number | null;
  block_rate: number | null;
  false_block_rate: number | null;
}

export interface QueryEvalResult {
  query: string;
  category: EvalCategory;
  expected_document_id: string | null;
  blocked: boolean;
  matched_rank: number | null;
  refused: boolean | null;
  answer_excerpt: string;
  guardrails: GuardrailVerdict[];
}

export interface EvalReport {
  generated_at: string;
  k: number;
  categories: CategoryMetrics[];
  results: QueryEvalResult[];
}

export async function runGuardrailEval(): Promise<EvalReport> {
  const response = await apiFetch(`${API_BASE}/eval/run`, { method: "POST" });
  return response.json();
}

export interface RankingMetrics {
  query_count: number;
  recall_at_1: number;
  recall_at_k: number;
  mrr: number;
  ndcg_at_k: number;
}

export interface RerankQueryResult {
  query: string;
  expected_document_filename: string;
  expected_excerpt: string | null;
  rank_in_pool: number | null;
  rank_before: number | null;
  rank_after: number | null;
  candidate_count: number;
  rerank_status: string;
  rerank_duration_ms: number | null;
}

export interface RerankComparisonReport {
  generated_at: string;
  model: string;
  search_mode: string;
  k: number;
  candidate_k: number;
  baseline: RankingMetrics;
  reranked: RankingMetrics;
  delta: RankingMetrics;
  pool_recall: number;
  improved_count: number;
  worsened_count: number;
  unchanged_count: number;
  rerank_failed_count: number;
  mean_rerank_ms: number | null;
  p95_rerank_ms: number | null;
  skipped_queries: string[];
  results: RerankQueryResult[];
}

export async function runRerankComparison(): Promise<RerankComparisonReport> {
  const response = await apiFetch(`${API_BASE}/eval/rerank-comparison`, { method: "POST" });
  return response.json();
}

// --- Conversations (server-side chat history; see backend routes_conversations.py) ---

export interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  standalone_question: string | null;
  cache_hit: boolean;
  // The assistant answer's response payload (citations, guardrails, evidence, retrieval).
  payload: ChatResponsePayload | null;
}

export interface ConversationDetailOut extends ConversationOut {
  messages: ConversationMessageOut[];
}

export async function fetchConversations(): Promise<ConversationOut[]> {
  const response = await apiFetch(`${API_BASE}/conversations`);
  return response.json();
}

export async function fetchConversation(conversationId: string): Promise<ConversationDetailOut> {
  const response = await apiFetch(`${API_BASE}/conversations/${conversationId}`);
  return response.json();
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await apiFetch(`${API_BASE}/conversations/${conversationId}`, { method: "DELETE" });
}

// --- Agents (UI test-generation pipeline) ---

export type AgentRunStatus = "queued" | "running" | "succeeded" | "failed" | "stale";

export interface AgentModelInfo {
  provider: string;
  model: string;
}

export interface AgentDefaults {
  target_url: string;
  requirement: string;
  allowed_target_hosts: string[];
  models: Record<string, AgentModelInfo>;
  max_design_rounds: number;
  active_run_id: string | null;
}

export interface AgentStepStatus {
  name: string;
  status: string;
  duration_ms: number | null;
}

export interface AgentRunSummary {
  run_id: string;
  status: AgentRunStatus;
  created_at: string;
  finished_at: string | null;
  username: string | null;
  target_url: string;
  current_step: string | null;
  error: string | null;
  passed: number | null;
  total: number | null;
  steps: AgentStepStatus[];
}

export interface AgentCheck {
  name: string;
  passed: boolean;
  severity: "error" | "warning";
  detail: string;
}

export interface AgentLlmCall {
  attempt: number;
  provider: string;
  model: string;
  response_format: string;
  messages: unknown[];
  raw_response: string | null;
  parse_error: string | null;
  validation_errors: unknown;
  valid?: boolean;
  error?: string;
  duration_ms?: number;
}

export interface AgentStepRecord {
  status?: string;
  input?: unknown;
  input_at?: string;
  output?: unknown;
  output_at?: string;
  duration_ms?: number;
  checks?: AgentCheck[];
  llm_calls?: AgentLlmCall[];
  error?: string;
  /** This agent's input/output Markdown files (paths inside agents/agents-result/); the
   * output file is parsed to build the next agent's input. */
  handoff?: AgentHandoff;
}

export interface AgentHandoff {
  input?: string;
  output?: string;
  /** Earlier agents' files this step's input was built from. */
  sources?: string[];
  /** Folder of files copied next to the output (screenshots, evidence, spec). */
  files?: string;
}

export interface ArtifactRef {
  name: string;
  bytes: number;
  sha256: string;
}

export interface AgentCaseReport {
  case_id: string;
  title: string;
  status: "passed" | "failed" | "error" | "not_run";
  source_rule_ids: string[];
  failed_step: number | null;
  error: string | null;
}

export interface AgentFailureAnalysis {
  case_id: string;
  suspected_cause: "app_defect" | "test_defect" | "environment";
  explanation: string;
}

export interface AgentReport {
  total: number;
  passed: number;
  failed: number;
  errored: number;
  pass_rate: number;
  cases: AgentCaseReport[];
  rule_coverage: Record<string, string[]>;
  rules_verified: string[];
  uncovered_rules: string[];
  dropped_cases: { case_id: string; title: string; reason: string }[];
  summary: string;
  failure_analysis: AgentFailureAnalysis[];
}

export interface AgentStepEvidence {
  index: number;
  action: string;
  value: string | null;
  status: "passed" | "failed" | "skipped";
  error: string | null;
  /** What the browser actually showed: element text, field value, visibility, URL. */
  observed: string | null;
  /** Messages visible on the page right after the step (alerts, success banner). */
  page_messages?: string[];
  evidence: ArtifactRef | null;
}

export interface AgentCaseRunResult {
  case_id: string;
  status: "passed" | "failed" | "error";
  duration_ms: number;
  steps: AgentStepEvidence[];
  failure_screenshot: ArtifactRef | null;
  console_errors: string[];
}

export interface AgentTestCaseSummary {
  case_id: string;
  title: string;
  /** Folder relative to the run folder, e.g. "test-cases/TC-REG-001". */
  folder: string;
  verdict: "approved" | "rejected" | null;
  result: "passed" | "failed" | "error" | null;
  evidence_count: number;
}

export interface AgentRunRecord {
  /** The run folder is pipeline-logs/agents/{log_file_stem}/. */
  log_file_stem: string;
  run_id: string;
  status: AgentRunStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
  target_url: string;
  requirement: string;
  models: Record<string, AgentModelInfo>;
  current_step: string | null;
  error: string | null;
  steps: Record<string, AgentStepRecord>;
  report: AgentReport | null;
  test_cases?: AgentTestCaseSummary[];
  design_rounds?: {
    round: number;
    designed: string[];
    approved: string[];
    rejected: string[];
    uncovered_rule_ids: string[];
  }[];
}

export interface AgentRunDetail {
  run_id: string;
  status: AgentRunStatus;
  record: AgentRunRecord;
}

export async function fetchAgentDefaults(): Promise<AgentDefaults> {
  const response = await apiFetch(`${API_BASE}/agents/defaults`);
  return response.json();
}

export async function startAgentRun(
  targetUrl: string,
  requirement: string,
): Promise<{ run_id: string; status: AgentRunStatus }> {
  const response = await apiFetch(`${API_BASE}/agents/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_url: targetUrl, requirement }),
  });
  return response.json();
}

export async function fetchAgentRuns(): Promise<AgentRunSummary[]> {
  const response = await apiFetch(`${API_BASE}/agents/runs`);
  return response.json();
}

export async function fetchAgentRun(runId: string): Promise<AgentRunDetail> {
  const response = await apiFetch(`${API_BASE}/agents/runs/${runId}`);
  return response.json();
}

/** Artifacts go through apiFetch (not a plain <img src>) because they need the
 * X-User-Id header: a run's files are only visible to its owner and admins. `name` is the
 * path inside the run folder, e.g. "test-cases/TC-REG-001/evidence/step-01-goto.png". */
export async function fetchAgentArtifact(runId: string, name: string): Promise<Blob> {
  const path = name.split("/").map(encodeURIComponent).join("/");
  const response = await apiFetch(`${API_BASE}/agents/runs/${runId}/artifacts/${path}`);
  return response.blob();
}

/** A per-agent handoff file of a run, `path` relative to agents/agents-result/. */
export async function fetchAgentHandoff(runId: string, path: string): Promise<Blob> {
  const encoded = path.split("/").map(encodeURIComponent).join("/");
  const response = await apiFetch(`${API_BASE}/agents/runs/${runId}/handoff/${encoded}`);
  return response.blob();
}

export { API_BASE };
