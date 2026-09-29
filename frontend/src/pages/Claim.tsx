import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, type Claim } from "../api";
import { useAuth } from "../auth";
import { useT, type Key } from "../i18n";
import { nice, toLocalInput, useAsync } from "../lib";
import { useRef_ } from "../ref";
import { ErrorBox, Loading, TrustBadge } from "../components/bits";

export function NewClaim() {
  const [p] = useSearchParams();
  const nav = useNavigate();
  const [err, setErr] = useState<Error | null>(null);
  useEffect(() => {
    const item = p.get("item");
    if (!item) return;
    api.createClaim({ item_id: item }).then((c) => nav(`/claims/${c.id}`, { replace: true })).catch(setErr);
  }, [p, nav]);
  return <main className="page" id="main">{err ? <ErrorBox error={err} /> : <Loading />}</main>;
}

function Questions({ claim, onDone }: { claim: Claim; onDone: (c: Claim) => void }) {
  const { t } = useT();
  const { zones } = useRef_();
  const [vals, setVals] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (id: string, v: string) => setVals((x) => ({ ...x, [id]: v }));
  const ready = claim.questions.every((q) => vals[q.id]?.trim());
  async function send() {
    setBusy(true); setErr("");
    try { onDone(await api.answer(claim.id, claim.questions.map((q) => ({ question_id: q.id, answer: q.kind === "datetime" ? new Date(vals[q.id]).toISOString() : vals[q.id] })))); }
    catch (x) { setErr((x as ApiError).message); }
    finally { setBusy(false); }
  }
  return (
    <div className="stack--lg stack">
      <p className="muted">{t("claim.intro")}</p>
      {claim.questions.map((q, n) => (
        <div className="q" key={q.id}>
          <span className="q__n">{String(n + 1).padStart(2, "0")}</span>
          <span className="h3" id={`q-${q.id}`}>{q.prompt}</span>
          {q.kind === "choice" && (
            <div className="choices" role="group" aria-labelledby={`q-${q.id}`}>
              {q.choices?.map((c) => <button key={c} type="button" className="choice" aria-pressed={vals[q.id] === c} onClick={() => set(q.id, c)}>{nice(c)}</button>)}
            </div>
          )}
          {q.kind === "text" && <input className="input" aria-labelledby={`q-${q.id}`} value={vals[q.id] ?? ""} onChange={(e) => set(q.id, e.target.value)} />}
          {q.kind === "zone" && (
            <select className="select" aria-labelledby={`q-${q.id}`} value={vals[q.id] ?? ""} onChange={(e) => set(q.id, e.target.value)}>
              <option value="">…</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          )}
          {q.kind === "datetime" && <input className="input" type="datetime-local" aria-labelledby={`q-${q.id}`} max={toLocalInput(new Date())} value={vals[q.id] ?? ""} onChange={(e) => set(q.id, e.target.value)} />}
        </div>
      ))}
      {err && <p className="err" role="alert">{err}</p>}
      <button className="btn btn--lost" disabled={!ready || busy} onClick={send}>{t("claim.submit")}</button>
    </div>
  );
}

function Tip({ claim, onDone }: { claim: Claim; onDone: (c: Claim) => void }) {
  const { t } = useT();
  const [amt, setAmt] = useState(50);
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  if (claim.tip) return <p className="banner banner--ok">{t("tip.done")}: {claim.tip.amount}</p>;
  return (
    <section className="stack" aria-labelledby="tip-h">
      <h2 className="h3" id="tip-h">{t("tip.title")}</h2>
      <p className="muted">{t("tip.hint")}</p>
      <div className="chips">{[20, 50, 100, 200].map((a) => <button key={a} className="chip" aria-pressed={amt === a} onClick={() => setAmt(a)}>{a}</button>)}</div>
      <input className="input" value={note} onChange={(e) => setNote(e.target.value)} placeholder="chai on me" maxLength={200} />
      {err && <p className="err">{err}</p>}
      <button className="btn btn--ghost" onClick={async () => { try { onDone(await api.tip(claim.id, amt, note)); } catch (x) { setErr((x as ApiError).message); } }}>{t("tip.send")} · {amt}</button>
    </section>
  );
}

const ISO = /^\d{4}-\d\d-\d\dT/;
function usePretty() {
  const { zoneName } = useRef_();
  return (v: unknown): string => {
    if (Array.isArray(v)) return v.map((x) => (x && typeof x === "object" ? (x as { value?: string }).value : x)).filter(Boolean).join(", ");
    if (v && typeof v === "object") return String((v as { value?: string }).value ?? "");
    const s = String(v ?? "");
    if (ISO.test(s)) return new Date(s).toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
    if (s.startsWith("z_")) return zoneName(s);
    return nice(s);
  };
}

function FinderReview({ claim, onDone }: { claim: Claim; onDone: (c: Claim) => void }) {
  const { t } = useT();
  const pretty = usePretty();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const decide = async (d: "approve" | "reject" | "more_info") => {
    setBusy(true); setErr("");
    try { onDone(await api.decide(claim.id, d)); } catch (x) { setErr((x as ApiError).message); } finally { setBusy(false); }
  };
  const r = claim.review;
  return (
    <div className="stack">
      {r && (
        <>
          <h2 className="h3">{t("claim.theirAnswers")}</h2>
          <dl className="review">
            {r.answers.map((a, i) => (
              <div key={i}>
                <dt>{a.prompt}</dt>
                <dd><strong>{pretty(a.answer)}</strong>{a.expected ? <span className="muted"> · {t("claim.have")}: {pretty(a.expected)}</span> : null}</dd>
              </div>
            ))}
          </dl>
          <h2 className="h3">{t("claim.yours")}</h2>
          <dl className="review">
            {Object.entries(r.private_details).map(([k, v]) => <div key={k}><dt>{nice(k)}</dt><dd>{pretty(v)}</dd></div>)}
          </dl>
        </>
      )}
      {claim.status === "pending_review" && (
        <div className="stack--sm stack">
          {err && <p className="err">{err}</p>}
          <div className="pair">
            <button className="btn btn--danger" disabled={busy} onClick={() => decide("reject")}>{t("claim.reject")}</button>
            <button className="btn btn--ink" disabled={busy} onClick={() => decide("approve")}>{t("claim.approve")}</button>
          </div>
          <button className="btn btn--quiet" disabled={busy} onClick={() => decide("more_info")}>{t("claim.ask")}</button>
        </div>
      )}
    </div>
  );
}

export default function ClaimPage() {
  const { id = "" } = useParams();
  const { t } = useT();
  const { user } = useAuth();
  const { data: claim, error, loading, reload, setData } = useAsync(() => api.claim(id), [id]);

  if (loading && !claim) return <main className="page" id="main"><Loading /></main>;
  if (error || !claim) return <main className="page" id="main"><ErrorBox error={error ?? new Error("Not found")} retry={reload} /></main>;
  const mine = claim.claimant_id === user?.id;
  const st = claim.status;
  const approved = ["approved", "auto_approved", "handed_over"].includes(st);

  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack--sm stack">
        <p className="eyebrow">{claim.item.ticket_no}</p>
        <h1 className="h2">{mine ? t("claim.title") : t("claim.finderTitle")}</h1>
        <p className="muted" style={{ textTransform: "capitalize" }}>{[claim.item.colors[0], claim.item.brand, nice(claim.item.category)].filter(Boolean).join(" ")}</p>
        {claim.counterpart && <span className="row"><span className="muted">{t(`role.${claim.counterpart.role}` as Key)}</span><TrustBadge trust={claim.counterpart.trust} /></span>}
      </div>

      {mine && (st === "draft" || st === "needs_more_info") && (
        <>
          {st === "needs_more_info" && <p className="banner banner--orange">{t("claim.more")}: {claim.note}</p>}
          <Questions claim={claim} onDone={setData} />
        </>
      )}
      {mine && st === "pending_review" && <p className="banner">{t("claim.pending")}</p>}
      {mine && st === "rejected" && <p className="banner banner--bad">{t("claim.rejected")} {claim.note}</p>}
      {approved && st !== "handed_over" && mine && <p className="banner banner--ok">{t("claim.approved")}</p>}
      {!mine && <FinderReview claim={claim} onDone={setData} />}

      {approved && (
        <div className="stack">
          {mine && st !== "handed_over" && <Link className="btn btn--lost" to={`/claims/${claim.id}/pass`}>{t("claim.pass")}</Link>}
          {st !== "handed_over" && <Link className="btn btn--ghost" to={`/claims/${claim.id}/chat`}>{mine ? t("claim.chat") : t("claim.chatOwner")}</Link>}
        </div>
      )}
      {mine && st === "handed_over" && <Tip claim={claim} onDone={setData} />}
    </main>
  );
}
