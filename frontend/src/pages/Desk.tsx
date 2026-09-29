import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useT } from "../i18n";
import { nice, useAsync, whenText } from "../lib";
import { useRef_ } from "../ref";
import { ErrorBox, Field, Loading } from "../components/bits";

export default function Desk() {
  const { t } = useT();
  const { zones } = useRef_();
  const queue = useAsync(() => api.adminClaims("pending_review"), []);
  const [code, setCode] = useState("");
  const [idOk, setIdOk] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [lines, setLines] = useState("");
  const [zone, setZone] = useState("");
  const [bulkMsg, setBulkMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function confirm() {
    setMsg(null);
    try { await api.confirmHandover({ code, id_checked: idOk }); setMsg({ ok: true, text: "Handed over." }); setCode(""); setIdOk(false); void queue.reload(); }
    catch (x) { setMsg({ ok: false, text: (x as ApiError).message }); }
  }
  async function bulk() {
    setBulkMsg(null);
    const rows = lines.split("\n").map((l) => l.trim()).filter(Boolean).map((text) => ({ text, zone_id: zone }));
    try { const r = await api.bulk(rows); setBulkMsg({ ok: true, text: `${r.created} logged.` }); setLines(""); }
    catch (x) { setBulkMsg({ ok: false, text: (x as ApiError).message }); }
  }
  return (
    <main className="page page--wide stack--lg stack" id="main">
      <h1 className="h2">{t("desk.title")}</h1>
      <div className="stack" style={{ maxWidth: 420 }}>
        <h2 className="h3">{t("desk.confirm")}</h2>
        <Field label={t("desk.code")}><input className="input input--code" inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
        <label className="row"><input type="checkbox" checked={idOk} onChange={(e) => setIdOk(e.target.checked)} /> {t("desk.idChecked")}</label>
        {msg && <p className={msg.ok ? "banner banner--ok" : "banner banner--bad"} role="status">{msg.text}</p>}
        <button className="btn btn--ink" disabled={code.length !== 6} onClick={confirm}>{t("desk.confirmBtn")}</button>
      </div>
      <section className="stack" aria-labelledby="dq">
        <h2 className="h3" id="dq">{t("desk.queue")}</h2>
        {queue.loading && !queue.data ? <Loading /> : queue.error ? <ErrorBox error={queue.error} retry={queue.reload} /> : !queue.data?.length ? <p className="empty">{t("desk.empty")}</p> : (
          <ul className="list">{queue.data.map((c) => (
            <li key={c.id}><Link to={`/claims/${c.id}`} className="li"><span className="li__body"><strong style={{ textTransform: "capitalize" }}>{nice(c.category)} · {c.ticket_no}</strong><span>{c.review?.claimant_email} · {whenText(c.created_at)}</span></span><span className="mono">{c.review?.score != null ? Math.round(c.review.score * 100) + "%" : ""}</span></Link></li>
          ))}</ul>
        )}
      </section>
      <div className="stack" style={{ maxWidth: 520 }}>
        <h2 className="h3">{t("desk.bulk")}</h2>
        <p className="muted">{t("desk.bulkHint")}</p>
        <Field label={t("desk.bulkZone")}><select className="select" value={zone} onChange={(e) => setZone(e.target.value)}><option value="">{t("report.choosePlace")}</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select></Field>
        <textarea className="textarea" rows={5} value={lines} onChange={(e) => setLines(e.target.value)} placeholder={t("desk.bulkPh")} aria-label={t("desk.bulk")} />
        {bulkMsg && <p className={bulkMsg.ok ? "banner banner--ok" : "banner banner--bad"} role="status">{bulkMsg.text}</p>}
        <button className="btn btn--ink" disabled={!lines.trim() || !zone} onClick={bulk}>{t("desk.bulkBtn")}</button>
      </div>
    </main>
  );
}
