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

export type PipelineName = "retrieval" | "indexing";

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

export { API_BASE };
