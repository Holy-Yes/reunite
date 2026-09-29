import { useEffect, useState, type FormEvent } from "react";
import QRCode from "qrcode";
import { api, ApiError, type Tag } from "../api";
import { useT } from "../i18n";
import { useAsync, whenText } from "../lib";
import { ErrorBox, Field, Loading } from "../components/bits";

function TagCard({ tag, onChange }: { tag: Tag; onChange: () => void }) {
  const { t } = useT();
  const url = `${location.origin}/t/${tag.code}`;
  const [qr, setQr] = useState("");
  const threads = useAsync(() => api.tagThreads(tag.id), [tag.id, tag.threads]);
  const [reply, setReply] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  useEffect(() => { void QRCode.toDataURL(url, { width: 240, margin: 1 }).then(setQr); }, [url]);

  async function send(th: string) {
    setErr("");
    try { await api.tagReply(tag.id, th, reply[th] ?? ""); setReply((r) => ({ ...r, [th]: "" })); await threads.reload(); }
    catch (x) { setErr((x as ApiError).message); }
  }
  return (
    <article className="stack card" style={{ padding: 16 }}>
      <div className="row row--between">
        <h2 className="h3">{tag.label}</h2>
        <span className={`tag ${tag.active ? "tag--ok" : ""}`}>{tag.active ? "on" : "off"}</span>
      </div>
      <div className="row row--wrap" style={{ gap: 16 }}>
        {qr && <img src={qr} alt={`QR code for ${tag.label}`} width={120} height={120} style={{ imageRendering: "pixelated" }} />}
        <div className="stack--sm stack">
          <p className="mono muted" style={{ overflowWrap: "anywhere" }}>{url}</p>
          <div className="row">
            <button className="btn btn--ghost" onClick={() => window.print()}>{t("tags.print")}</button>
            <button className="btn btn--quiet" onClick={async () => { await api.setTagActive(tag.id, !tag.active); onChange(); }}>{tag.active ? t("tags.off") : t("tags.on")}</button>
          </div>
        </div>
      </div>
      {threads.data?.map((th) => (
        <div key={th.thread_id} className="stack--sm stack">
          <hr className="rule" />
          <div className="chat">
            {th.messages.map((m) => <div key={m.id} className={`bubble ${m.sender === "owner" ? "bubble--me" : "bubble--them"}`}>{m.body}<small>{whenText(m.at)}</small></div>)}
          </div>
          <div className="row">
            <input className="input" value={reply[th.thread_id] ?? ""} onChange={(e) => setReply((r) => ({ ...r, [th.thread_id]: e.target.value }))} placeholder={t("tags.replyPh")} aria-label={t("tags.replyPh")} />
            <button className="btn btn--ink" disabled={!(reply[th.thread_id] ?? "").trim()} onClick={() => send(th.thread_id)}>{t("chat.send")}</button>
          </div>
        </div>
      ))}
      {err && <p className="err" role="alert">{err}</p>}
    </article>
  );
}

export default function Tags() {
  const { t } = useT();
  const tags = useAsync(() => api.tags(), []);
  const [label, setLabel] = useState("");
  const [err, setErr] = useState("");

  async function add(e: FormEvent) {
    e.preventDefault();
    setErr("");
    try { await api.newTag(label); setLabel(""); await tags.reload(); }
    catch (x) { setErr((x as ApiError).message); }
  }
  useEffect(() => {
    const i = setInterval(() => void tags.reload(), 15000);
    return () => clearInterval(i);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack--sm stack">
        <h1 className="h2">{t("tags.title")}</h1>
        <p className="muted">{t("tags.intro")}</p>
      </div>
      <form className="stack" onSubmit={add}>
        <Field label={t("tags.name")} error={err}><input className="input" value={label} maxLength={80} onChange={(e) => setLabel(e.target.value)} placeholder={t("tags.namePh")} /></Field>
        <button className="btn btn--ink" disabled={!label.trim()}>{t("tags.add")}</button>
      </form>
      {tags.loading && !tags.data ? <Loading /> : tags.error ? <ErrorBox error={tags.error} retry={tags.reload} /> : !tags.data?.length ? <p className="empty">{t("tags.empty")}</p> : (
        <div className="stack">{tags.data.map((tg) => <TagCard key={tg.id} tag={tg} onChange={tags.reload} />)}</div>
      )}
    </main>
  );
}
