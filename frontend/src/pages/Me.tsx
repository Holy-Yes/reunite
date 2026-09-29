import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import { LANGS, useT } from "../i18n";
import { useAsync } from "../lib";
import { Field, TrustBadge } from "../components/bits";

export default function Me() {
  const { t, lang, setLang } = useT();
  const { user, signOut, refresh } = useAuth();
  const trust = useAsync(() => api.myTrust(), []);
  const [roll, setRoll] = useState(user?.roll_no ?? "");
  const [msg, setMsg] = useState("");
  useEffect(() => setRoll(user?.roll_no ?? ""), [user?.roll_no]);
  async function save() {
    setMsg("");
    try { await api.updateMe({ roll_no: roll }); await refresh(); setMsg("Saved"); } catch (x) { setMsg((x as ApiError).message); }
  }
  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack--sm stack">
        <h1 className="h2">{t("me.title")}</h1>
        <p className="muted">{user?.email} · {user?.role}</p>
      </div>
      {trust.data && (
        <section className="stack--sm stack" aria-labelledby="tr">
          <h2 className="h3" id="tr">{t("me.trust")}</h2>
          <TrustBadge trust={trust.data} />
          <p className="muted">{trust.data.items_returned} {t("trust.returned")} · {trust.data.claims_approved} {t("trust.approved")} · {trust.data.points} {t("trust.points")}</p>
        </section>
      )}
      <Field label={t("me.roll")} error={msg && msg !== "Saved" ? msg : undefined}>
        <div className="row">
          <input className="input" value={roll} onChange={(e) => setRoll(e.target.value.toUpperCase())} placeholder="21071A0542" maxLength={10} />
          <button className="btn btn--ink" onClick={save}>{t("me.save")}</button>
        </div>
      </Field>
      {msg === "Saved" && <p className="banner banner--ok" role="status">{msg}</p>}
      <div className="field">
        <span className="label">{t("me.language")}</span>
        <div className="chips">{LANGS.map((l) => <button key={l.id} className="chip" aria-pressed={lang === l.id} onClick={() => setLang(l.id)}>{l.label}</button>)}</div>
      </div>
      <label className="row"><input type="checkbox" checked={!!user?.notify_email} onChange={async (e) => { await api.updateMe({ notify_email: e.target.checked }); await refresh(); }} /> {t("me.emailAlerts")}</label>
      <Link className="btn btn--ghost" to="/tags">{t("tags.link")}</Link>
      <button className="btn btn--ghost" onClick={signOut}>{t("me.signout")}</button>
    </main>
  );
}
