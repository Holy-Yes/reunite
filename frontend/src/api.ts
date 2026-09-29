// Typed client for the FastAPI backend. Every call goes through `req`, which adds the token and turns
// the backend's error envelope into an ApiError the screens can show as plain text.

export type Band = "strong" | "possible" | "long_shot";
export type Attr = { value: string; confidence: number; source: string; hidden?: boolean };
export type Attributes = {
  category?: Attr | null;
  brand?: Attr | null;
  material?: Attr | null;
  serial?: Attr | null;
  colors?: Attr[];
  marks?: Attr[];
};
export type User = { id: string; email: string; role: "student" | "desk" | "admin" | "security_guard"; roll_no: string | null; points: number; venue: string | null; notify_email: boolean; notify_push: boolean };
export type Item = {
  id: string; ticket_no: string; kind: "lost" | "found"; status: string; description: string; attributes: Attributes;
  photos: { id: string; url: string }[]; zone_id: string; occurred_from: string; occurred_to: string;
  custody_zone_id: string | null; lat?: number | null; lon?: number | null; redacted: boolean; routed_to: string | null; match_count: number; created_at: string;
};
export type PublicItem = { id: string; ticket_no: string; category: string | null; colors: string[]; brand?: string; zone_id: string; found_at: string; photo?: { url: string; blurred: boolean }; redacted?: boolean };
export type Why = { key: string; label: string; contribution: number; value: number; weight: number; state: "match" | "partial" | "mismatch" | "not_compared"; detail: string };
export type Match = { id: string; lost_item_id: string; candidate: PublicItem; score: number; band: Band; rank: number; why: Why[]; feedback: string | null };
export type Question = { id: string; prompt: string; kind: "text" | "choice" | "zone" | "datetime"; choices?: string[] };
export type Trust = { score: number; level: "new" | "ok" | "trusted" | "low"; items_returned: number; claims_approved: number; claims_rejected: number; points: number };
export type Claim = {
  id: string; item_id: string; claimant_id: string; status: string; questions: Question[]; note: string | null; item: PublicItem;
  must_be_reviewed_by_person: boolean; created_at: string; chat_open?: boolean;
  counterpart?: { role: "finder" | "owner"; trust: Trust }; tip?: { amount: number; note: string | null };
  review?: { score: number | null; answers: { prompt: string; answer: string; expected?: string; score?: number }[]; private_details: Record<string, unknown>; claimant_email: string };
  category?: string; ticket_no?: string;
};
export type Handover = { claim_id: string; qr_payload: string; code: string; expires_at: string; expired: boolean; collect_zone_id: string };
export type Alert = { id: string; type: string; title: string; body: string; href: string; read: boolean; at: string };
export type ChatMessage = { id: string; sender: "owner" | "finder" | "desk"; mine: boolean; body: string; at: string };
export type TimelineEvent = { id: string; type: string; actor_role: string; at: string; note?: string };
export type Zone = { id: string; name: string; short_name: string; kind: string; centroid?: [number, number] };
export type Taxonomy = { categories: { id: string; group: string }[]; brands: string[]; colors: { name: string; hex: string }[]; marks: string[] };
export type Extraction = { attributes: Attributes; ocr_text?: string; zone_hint?: string | { value: string; confidence: number } | null; suspected_id_card?: boolean };

export type Tag = { id: string; code: string; label: string; active: boolean; threads: number };
export type TagMsg = { id: string; sender: "finder" | "owner"; body: string; at: string };
export type TagThread = { thread_id: string; messages: TagMsg[] };

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public fields: Record<string, string> = {}) {
    super(message);
  }
}

const KEY = "reunite.token";
export const token = {
  get: () => { try { return localStorage.getItem(KEY); } catch { return null; } },
  set: (t: string | null) => { try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch { /* private mode */ } },
};

type Opts = { method?: string; json?: unknown; form?: FormData; query?: Record<string, string | undefined> };

async function req<T>(path: string, o: Opts = {}): Promise<T> {
  const q = o.query ? "?" + new URLSearchParams(Object.entries(o.query).filter(([, v]) => v) as [string, string][]) : "";
  const headers: Record<string, string> = {};
  const t = token.get();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body: BodyInit | undefined;
  if (o.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(o.json); }
  if (o.form) body = o.form;
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}${q}`, { method: o.method ?? (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError(0, "offline", "No connection. Your draft is safe; try again when you're back online.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error ?? {};
    if (res.status === 401 && t) { token.set(null); window.dispatchEvent(new Event("reunite:signout")); }
    throw new ApiError(res.status, e.code ?? "error", e.message ?? "Something went wrong. Try again.", e.fields ?? {});
  }
  return data as T;
}

export const api = {
  authConfig: () => req<{ demo_otp: string | null }>("/auth/config"),
  requestCode: (email: string) => req<void>("/auth/otp/request", { json: { email } }),
  verifyCode: (email: string, code: string) => req<{ token: string; user: User }>("/auth/otp/verify", { json: { email, code } }),
  me: () => req<User>("/me"),
  updateMe: (b: Partial<{ roll_no: string; notify_email: boolean; venue: string }>) => req<User>("/me", { method: "PATCH", json: b }),
  myTrust: () => req<Trust>("/users/me/trust"),
  taxonomy: () => req<Taxonomy>("/taxonomy"),
  zones: () => req<{ features: { properties: Zone }[] }>("/zones"),
  extract: (f: FormData) => req<Extraction>("/items/extract-preview", { form: f }),
  createItem: (f: FormData) => req<Item>("/items", { form: f }),
  items: () => req<Item[]>("/items", { query: { mine: "1" } }),
  item: (id: string) => req<Item>(`/items/${id}`),
  events: (id: string) => req<TimelineEvent[]>(`/items/${id}/events`),
  closeItem: (id: string, reason?: string) => req<Item>(`/items/${id}/close`, { json: { reason } }),
  publicItems: (q?: string) => req<PublicItem[]>("/items/public", { query: { q } }),
  bulk: (items: { text: string; zone_id: string }[]) => req<{ created: number }>("/items/bulk", { json: { items } }),
  matches: () => req<Match[]>("/matches", { query: { status: "pending" } }),
  feedback: (id: string, verdict: "mine" | "not_mine" | "unsure") => req<Match>(`/matches/${id}/feedback`, { json: { verdict } }),
  createClaim: (b: { match_id?: string; item_id?: string }) => req<Claim>("/claims", { json: b }),
  claims: (role?: "claimant" | "finder") => req<Claim[]>("/claims", { query: { role } }),
  claim: (id: string) => req<Claim>(`/claims/${id}`),
  answer: (id: string, answers: { question_id: string; answer: string }[]) => req<Claim>(`/claims/${id}/answers`, { json: { answers } }),
  decide: (id: string, decision: "approve" | "reject" | "more_info", note?: string) => req<Claim>(`/claims/${id}/decision`, { json: { decision, note } }),
  handover: (id: string) => req<Handover>(`/claims/${id}/handover`),
  newHandover: (id: string) => req<Handover>(`/claims/${id}/handover`, { method: "POST" }),
  confirmHandover: (b: { code?: string; token?: string; id_checked: boolean }) => req<{ claim: Claim; item: Item }>("/handover/confirm", { json: b }),
  messages: (id: string) => req<ChatMessage[]>(`/claims/${id}/messages`),
  send: (id: string, body: string) => req<ChatMessage>(`/claims/${id}/messages`, { json: { body } }),
  tip: (id: string, amount: number, note?: string) => req<Claim>(`/claims/${id}/tip`, { json: { amount, note } }),
  alerts: () => req<Alert[]>("/notifications"),
  readAll: () => req<void>("/notifications/read-all", { method: "POST" }),
  readAlert: (id: string) => req<void>(`/notifications/${id}/read`, { method: "POST" }),
  tags: () => req<Tag[]>("/tags"),
  newTag: (label: string) => req<Tag>("/tags", { json: { label } }),
  setTagActive: (id: string, active: boolean) => req<Tag>(`/tags/${id}`, { method: "PATCH", json: { active } }),
  tagThreads: (id: string) => req<TagThread[]>(`/tags/${id}/threads`),
  tagReply: (id: string, thread: string, body: string) => req<TagThread>(`/tags/${id}/threads/${thread}/reply`, { json: { body } }),
  publicTag: (code: string) => req<{ label: string }>(`/public/tags/${code}`),
  publicTagSend: (code: string, body: string, thread_id?: string) => req<TagThread>(`/public/tags/${code}/messages`, { json: { body, thread_id } }),
  publicTagThread: (code: string, thread: string) => req<TagThread>(`/public/tags/${code}/threads/${thread}`),
  adminClaims: (status?: string) => req<Claim[]>("/admin/claims", { query: { status } }),
};
