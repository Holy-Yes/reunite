import { useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError, type TagThread } from "../api";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { useAsync, whenText } from "../lib";
import { ErrorBox, Loading } from "../components/bits";

// No account and no app: the thread id is the finder's only key, kept in this browser.
const key = (code: string) => `reunite.tag.${code}`;
const read = (code: string) => { try { return localStorage.getItem(key(code)); } catch { return null; } };

export default function PublicTag() {
  const { code = "" } = useParams();
  const { t } = useT();
  const tag = useAsync(() => api.publicTag(code), [code]);
  const [thread, setThread] = useState<TagThread | null>(null);
  const [body, setBody] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const [threadId, setThreadId] = useState<string | null>(() => read(code));
  useEffect(() => {
    if (!threadId) return;
    const load = () => api.publicTagThread(code, threadId).then(setThread).catch(() => {});
    void load();
    const i = setInterval(load, 8000);
    return () => clearInterval(i);
  }, [code, threadId]);

  async function send(e: FormEvent) {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true); setErr("");
    try {
      const th = await api.publicTagSend(code, body, thread?.thread_id);
      try { localStorage.setItem(key(code), th.thread_id); } catch { /* private mode: the reply won't persist */ }
      setThread(th); setThreadId(th.thread_id); setBody("");
    } catch (x) { setErr((x as ApiError).message); }
    finally { setBusy(false); }
  }

  if (tag.loading && !tag.data) return <main className="page" id="main"><Loading /></main>;
  if (tag.error || !tag.data) return <main className="page stack" id="main"><p className="banner banner--bad">{t("pub.gone")}</p></main>;
  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack--sm stack">
        <p className="eyebrow">{tag.data.label}</p>
        <h1 className="h1">{t("pub.title")}</h1>
        <p className="muted">{t("pub.intro")}</p>
      </div>
      {!!thread?.messages.length && (
        <div className="chat" role="log" aria-live="polite">
          {thread.messages.map((m) => (
            <div key={m.id} className={`bubble ${m.sender === "finder" ? "bubble--me" : "bubble--them"}`}>
              {m.body}<small>{m.sender === "finder" ? t("pub.you") : t("pub.owner")} · {whenText(m.at)}</small>
            </div>
          ))}
        </div>
      )}
      {thread && <p className="banner banner--ok">{t("pub.sent")}</p>}
      <form className="stack" onSubmit={send}>
        <textarea className="textarea" value={body} maxLength={500} onChange={(e) => setBody(e.target.value)} placeholder={t("pub.ph")} aria-label={t("pub.ph")} />
        {err && <p className="err" role="alert">{err}</p>}
        <button className="btn btn--lost" disabled={busy || !body.trim()}><Icon n="send" /> {t("pub.send")}</button>
      </form>
    </main>
  );
}
