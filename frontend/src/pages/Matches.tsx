import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError, type Match } from "../api";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { nice, useAsync, whenText } from "../lib";
import { useRef_ } from "../ref";
import { BandTag, ErrorBox, Loading } from "../components/bits";

export default function Matches() {
  const { t } = useT();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const { zoneName } = useRef_();
  const list = useAsync(() => api.matches(), []);
  const [i, setI] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const only = params.get("item");
  const all: Match[] = (list.data ?? []).filter((m) => !only || m.lost_item_id === only);
  const m = all[i];

  async function mine() {
    if (!m || busy) return;
    setBusy(true); setErr("");
    try { const c = await api.createClaim({ match_id: m.id }); nav(`/claims/${c.id}`); }
    catch (x) { setErr((x as ApiError).message); setBusy(false); }
  }
  async function notMine() {
    if (!m || busy) return;
    setBusy(true); setErr("");
    try { await api.feedback(m.id, "not_mine"); setI((n) => n + 1); }
    catch (x) { setErr((x as ApiError).message); }
    finally { setBusy(false); }
  }
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).closest("input,textarea,select")) return;
      if (e.key === "ArrowRight") void mine();
      if (e.key === "ArrowLeft") void notMine();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack--sm stack">
        <h1 className="h2">{t("matches.title")}</h1>
        {all.length > 0 && m && <p className="muted mono">{Math.min(i + 1, all.length)} / {all.length}</p>}
      </div>
      {list.loading && !list.data ? <Loading /> : list.error ? <ErrorBox error={list.error} retry={list.reload} /> : !m ? (
        <p className="empty">{t("matches.empty")}</p>
      ) : (
        <article className="card" aria-live="polite">
          <div className="card__photo">
            {m.candidate.photo ? <img src={m.candidate.photo.url} alt="" /> : <Icon n="image" size={48} />}
          </div>
          <div className="card__body">
            <div className="row row--between">
              <div>
                <h2 className="h2" style={{ textTransform: "capitalize" }}>{[m.candidate.colors[0], m.candidate.brand, nice(m.candidate.category)].filter(Boolean).join(" ")}</h2>
                <p className="muted">{zoneName(m.candidate.zone_id)} · {whenText(m.candidate.found_at)}</p>
              </div>
              <BandTag band={m.band} />
            </div>
            <div className="score"><b>{Math.round(m.score * 100)}%</b><span className="muted">{t("matches.why")}</span></div>
            <ul className="why">
              {m.why.map((w) => (
                <li key={w.key}>
                  <span>{w.label}</span>
                  <span className="bar" aria-hidden="true"><i data-s={w.state} style={{ width: w.state === "not_compared" ? "0%" : `${Math.max(4, Math.round(w.value * 100))}%` }} /></span>
                  <span className="mono">{w.state === "not_compared" ? "–" : `${Math.round(w.value * 100)}`}</span>
                  <span className="why__d">{w.detail}</span>
                </li>
              ))}
            </ul>
            {m.candidate.photo && <p className="muted">{t("matches.photoNote")}</p>}
          </div>
        </article>
      )}
      {err && <p className="err" role="alert">{err}</p>}
      {m && (
        <div className="pair">
          <button className="btn btn--ghost" disabled={busy} onClick={notMine}><Icon n="x" /> {t("matches.notMine")}</button>
          <button className="btn btn--lost" disabled={busy} onClick={mine}><Icon n="check" /> {t("matches.mine")}</button>
        </div>
      )}
    </main>
  );
}
