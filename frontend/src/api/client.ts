import { useAuthStore } from "@/store/authStore";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:4000";

function getSessionId(): string {
  const key = "legal-ai-session-id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Session-Id": getSessionId(),
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  const body = await res.json().catch(() => ({}));

  if (!res.ok) {
    throw new ApiError(res.status, body.error ?? `request failed (${res.status})`);
  }
  return body as T;
}

export interface AuthUser {
  user_id: number;
  username: string;
  email: string;
  legal_expertise: "law" | "non_law" | null;
  created_at: string;
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export function register(input: {
  username: string;
  email: string;
  password: string;
  legalExpertise: "law" | "non_law";
}) {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function login(input: { username: string; password: string }) {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export interface CaseResult {
  case_id: string;
  case_name: string;
  citation: string;
  score: number;
  highlighted_html: string;
  verified: boolean | null;
}

export type RetrievalStrategy = "dense" | "hybrid" | "balanced" | "stance_aware";

export interface StrategyInfo {
  label: string;
  blurb: string;
  /** Number of OpenAI calls this strategy makes per query, before any answer generation. */
  llmCalls: number;
}

export const STRATEGIES: Record<RetrievalStrategy, StrategyInfo> = {
  dense: {
    label: "Dense (vector only)",
    blurb: "Embedding similarity alone. Fastest, free.",
    llmCalls: 0,
  },
  hybrid: {
    label: "Hybrid (dense + BM25)",
    blurb: "Fuses vector and keyword rankings via Reciprocal Rank Fusion. Free.",
    llmCalls: 0,
  },
  balanced: {
    label: "Balanced (adverse-aware)",
    blurb:
      "Hybrid pool, then an LLM labels each case favorable/adverse and promotes adverse ones into the top-k.",
    llmCalls: 1,
  },
  stance_aware: {
    label: "Stance-aware (widest pool)",
    blurb:
      "Also rewrites the query into supporting/adverse variants and fuses six rankings before the same promotion step.",
    llmCalls: 2,
  },
};

export interface LegalAnalysisResponse {
  query: string;
  answer: string | null;
  cases: CaseResult[];
  latency_ms: number;
  model: string;
  strategy: RetrievalStrategy;
  /** "similarity" = cosine (0-1). "rrf" = fusion score; rank-meaningful only, never a similarity. */
  score_type: string;
  queryId: number;
}

export function legalAnalysis(input: {
  query: string;
  k: number;
  useLlm: boolean;
  strategy: RetrievalStrategy;
}) {
  return request<LegalAnalysisResponse>("/legal-analysis", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function submitFeedback(input: { queryId: number; rating: number; comment?: string }) {
  return request<{ feedback_id: number; created_at: string }>("/feedback", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export interface HistoryItem {
  query_id: number;
  query: string;
  model: string;
  latency_ms: number;
  created_at: string;
  rating: number | null;
  comment: string | null;
}

export function getHistory() {
  return request<HistoryItem[]>("/history");
}
