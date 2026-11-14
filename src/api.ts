export type Profile = {
  name: string; kind: string; aliases: string[]; description: string; website: string;
  region: string; industry: string; priorities: string;
};

export type Choice = { value: string | null; confidence: number | null; probabilities: Record<string, number> };
export type Noul = { value: boolean | null; p_yes: number | null; confidence: number | null };
export type Decisions = {
  is_subject: Noul; category: Choice; report_type: Choice; is_novel: Noul; action: Choice;
  urgency: { score: number | null; confidence: number | null; probabilities: Record<string, number>; legend?: string[] };
};

export type Item = {
  id: string; url: string; canonical_url?: string; title: string; outlet?: string; published_at?: string | null;
  retrieved_at?: string; text?: string; source?: "live" | "fixture";
  facts?: any; ndi?: { job_id?: string; cached?: boolean; latency_ms?: number; cost?: number | null };
  decisions?: Decisions; final_action?: string; flags?: string[];
  evidence?: { passage: string | null; verified: boolean; origin: string | null; note?: string };
  drex?: { model?: string; latency_ms?: number; usage?: any; request_id?: string };
  explanation?: string; error?: string;
};

export class ApiFailure extends Error {
  constructor(message: string, public missingEnv?: string, public service?: string) { super(message); }
}

export async function api<T = any>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/${path}`, body === undefined ? undefined : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  let data: any = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw new ApiFailure(data?.error || `HTTP ${res.status}`, data?.missing_env, data?.service);
  return data as T;
}

export const ACTION_RANK: Record<string, number> = { review_now: 3, watch: 2, digest: 1, ignore: 0 };
export const ACTION_LABEL: Record<string, string> = {
  review_now: "Review now", watch: "Watch", digest: "Digest", ignore: "Ignore",
};

export function load<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem(key); return v ? (JSON.parse(v) as T) : fallback; } catch { return fallback; }
}
export function save(key: string, value: unknown) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* storage unavailable */ }
}
