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

export interface LegalAnalysisResponse {
  query: string;
  answer: string | null;
  cases: CaseResult[];
  latency_ms: number;
  model: string;
  queryId: number;
}

export function legalAnalysis(input: { query: string; k: number; useLlm: boolean }) {
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
