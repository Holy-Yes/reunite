import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { useAsync, whenText } from "../lib";
import { ErrorBox, Loading } from "../components/bits";

export default function Chat() {
  const { id = "" } = useParams();
  const { t } = useT();
  const msgs = useAsync(() => api.messages(id), [id]);
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const i = setInterval(() => void msgs.reload(), 5000);
    return () => clearInterval(i);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs.data?.length]);

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setErr("");
    try { await api.send(id, body); setBody(""); await msgs.reload(); }
    catch (x) { setErr((x as ApiError).message); }
  }
  const locked = msgs.error instanceof ApiError && msgs.error.code === "chat_locked";
  return (
    <main className="page stack" id="main">
      <div className="stack--sm stack">
        <h1 className="h2">{t("chat.title")}</h1>
        <p className="banner banner--orange"><Icon n="lock" size={14} /> {t("chat.hint")}</p>
      </div>
      {msgs.loading && !msgs.data ? <Loading /> : locked ? <p className="banner">{t("chat.locked")}</p> : msgs.error ? <ErrorBox error={msgs.error} retry={msgs.reload} /> : (
        <div className="chat" role="log" aria-live="polite">
          {msgs.data?.map((m) => (
            <div key={m.id} className={`bubble ${m.mine ? "bubble--me" : "bubble--them"}`}>
              {m.body}<small>{m.mine ? "" : `${m.sender} · `}{whenText(m.at)}</small>
            </div>
          ))}
          <div ref={end} />
        </div>
      )}
      {!locked && (
        <form className="compose" onSubmit={send}>
          <input className="input" value={body} maxLength={500} onChange={(e) => setBody(e.target.value)} placeholder={t("chat.ph")} aria-label={t("chat.ph")} />
          <button className="btn btn--ink" aria-label={t("chat.send")} disabled={!body.trim()}><Icon n="send" /></button>
        </form>
      )}
      {err && <p className="err" role="alert">{err}</p>}
      <Link className="btn btn--quiet" to={`/claims/${id}`}>{t("report.back")}</Link>
    </main>
  );
}
