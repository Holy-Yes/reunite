import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError, type Attr, type Attributes, type Item } from "../api";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { nice, toLocalInput } from "../lib";
import { useRef_ } from "../ref";
import PlaceMap from "../components/PlaceMap";
import { Field } from "../components/bits";

const src = (value: string, hidden?: boolean): Attr => ({ value, confidence: 1, source: "user", ...(hidden ? { hidden: true } : {}) });

export default function Report() {
  const { kind: k } = useParams();
  const kind = k === "found" ? "found" : "lost";
  const { t } = useT();
  const { zones, tax, zoneName } = useRef_();

  const [step, setStep] = useState(1);
  const [photos, setPhotos] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [text, setText] = useState("");
  const [attrs, setAttrs] = useState<Attributes>({});
  const [reading, setReading] = useState(false);
  const [zone, setZone] = useState("");
  const [pin, setPin] = useState<{ lat: number; lon: number } | null>(null);
  const [aim, setAim] = useState<{ lat: number; lon: number } | null>(null); // where the map flies: set by the place list, not by taps
  const [custody, setCustody] = useState("");
  const [whenKey, setWhenKey] = useState<"now" | "today" | "yesterday" | "pick">("now");
  const [picked, setPicked] = useState(toLocalInput(new Date()));
  const [markDraft, setMarkDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [done, setDone] = useState<Item | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setStep(1); setAttrs({}); setPhotos([]); setText(""); setDone(null); }, [kind]);
  useEffect(() => {
    const urls = photos.map((p) => URL.createObjectURL(p));
    setPreviews(urls);
    return () => urls.forEach((u) => URL.revokeObjectURL(u));
  }, [photos]);

  const centreOf = (id: string) => {
    const c = zones.find((z) => z.id === id)?.centroid;
    return c ? { lat: c[1], lon: c[0] } : null;
  };
  // A place from the list puts the pin at its centre; a tap on the map picks the nearest place.
  const chooseZone = (id: string) => { setZone(id); const c = centreOf(id); setPin(c); setAim(c); };
  const tapMap = (lat: number, lon: number) => {
    setPin({ lat, lon });
    let best = "", bestD = Infinity;
    for (const z of zones) {
      if (!z.centroid) continue;
      const dy = (z.centroid[1] - lat) * 110540, dx = (z.centroid[0] - lon) * 111320 * Math.cos((lat * Math.PI) / 180);
      const d = dx * dx + dy * dy;
      if (d < bestD) { best = z.id; bestD = d; }
    }
    if (best) setZone(best);
  };
  useEffect(() => { if (zone && !pin) { const c = centreOf(zone); setPin(c); setAim(c); } }, [zone, zones]); // eslint-disable-line react-hooks/exhaustive-deps

  const cats = useMemo(() => tax?.categories.map((c) => c.id) ?? [], [tax]);
  const lost = kind === "lost";

  async function toDetails() {
    if (!photos.length && !text.trim()) { setErr(t("report.needSomething")); return; }
    setErr(""); setReading(true); setStep(2);
    try {
      const f = new FormData();
      f.set("kind", kind); f.set("text", text);
      photos.forEach((p) => f.append("photos", p));
      const ex = await api.extract(f);
      setAttrs(ex.attributes);
      // The backend sends { value, confidence }; older builds sent a bare id.
      const hint = typeof ex.zone_hint === "string" ? ex.zone_hint : ex.zone_hint?.value;
      if (hint && zones.some((z) => z.id === hint)) setZone(hint);
    } catch (x) { setErr((x as ApiError).message); }
    finally { setReading(false); }
  }

  const setHidden = (field: "marks" | "serial", idx: number, hidden: boolean) =>
    setAttrs((a) => {
      if (field === "serial") return a.serial ? { ...a, serial: { ...a.serial, hidden: hidden || undefined } } : a;
      return { ...a, marks: (a.marks ?? []).map((m, i) => (i === idx ? { ...m, hidden: hidden || undefined } : m)) };
    });

  function range(): [Date, Date] {
    const now = new Date();
    if (whenKey === "now") return [now, now];
    if (whenKey === "today") { const s = new Date(now); s.setHours(6, 0, 0, 0); return [s, now]; }
    if (whenKey === "yesterday") { const s = new Date(now); s.setDate(s.getDate() - 1); s.setHours(6, 0, 0, 0); const e = new Date(s); e.setHours(23, 0, 0, 0); return [s, e]; }
    const p = new Date(picked);
    return [p, p];
  }

  async function submit() {
    setBusy(true); setErr("");
    try {
      const [from, to] = range();
      const f = new FormData();
      f.set("kind", kind); f.set("text", text || attrs.category?.value?.replace(/_/g, " ") || "");
      f.set("zone_id", zone); if (pin) { f.set("lat", String(pin.lat)); f.set("lon", String(pin.lon)); }
      f.set("occurred_from", from.toISOString()); f.set("occurred_to", to.toISOString());
      if (!lost && custody) f.set("custody_zone_id", custody);
      f.set("attributes", JSON.stringify(attrs));
      photos.forEach((p) => f.append("photos", p));
      setDone(await api.createItem(f));
    } catch (x) { setErr((x as ApiError).message); }
    finally { setBusy(false); }
  }

  if (done) {
    return (
      <main className="page done" id="main">
        <span className="eyebrow">{lost ? "Lost" : "Found"}</span>
        <h1 className="h1">{t("report.done")}</h1>
        <span className="ticket">{done.ticket_no}</span>
        <p className="muted">{t("report.doneBody")}</p>
        <div className="stack">
          <Link className="btn btn--lost" to={lost ? "/matches" : `/items/${done.id}`}>{lost ? t("report.seeMatches") : t("nav.home")}</Link>
          <Link className="btn btn--quiet" to="/home">{t("nav.home")}</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack">
        <div className="steps" aria-hidden="true">{[1, 2, 3].map((n) => <i key={n} data-on={n <= step ? "" : undefined} data-lost={lost ? "" : undefined} />)}</div>
        <p className="eyebrow eyebrow--quiet">{t("report.step")} {step} {t("report.of")} 3 · {t(`report.s${step}` as "report.s1")}</p>
        <h1 className="h2">{lost ? t("report.lostTitle") : t("report.foundTitle")}</h1>
      </div>

      {step === 1 && (
        <div className="stack">
          <label className="drop">
            <input ref={fileRef} type="file" accept="image/*" capture="environment" multiple onChange={(e) => setPhotos(Array.from(e.target.files ?? []).slice(0, 3))} />
            {previews.length ? <div className="thumbs">{previews.map((u) => <img key={u} src={u} alt="" />)}</div> : <Icon n="camera" size={40} />}
            <strong>{photos.length ? t("report.photoAdd") : t("report.photo")}</strong>
          </label>
          <Field label={t("report.words")}>
            <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("report.wordsPh")} />
          </Field>
          {err && <p className="err" role="alert">{err}</p>}
          <button className="btn btn--ink" onClick={toDetails}>{t("report.next")}</button>
        </div>
      )}

      {step === 2 && (
        <div className="stack">
          {reading ? <p className="muted row" role="status"><span className="spin" /> {t("report.reading")}</p> : <p className="muted">{t("report.chipsHint")}</p>}
          {err && <p className="err" role="alert">{err}</p>}
          <Field label={t("report.category")}>
            <select className="select" value={attrs.category?.value ?? ""} onChange={(e) => setAttrs({ ...attrs, category: e.target.value ? src(e.target.value) : null })}>
              <option value="">…</option>
              {cats.map((c) => <option key={c} value={c}>{nice(c)}</option>)}
            </select>
          </Field>
          <Field label={t("report.brand")}>
            <input className="input" list="brands" value={attrs.brand?.value ?? ""} onChange={(e) => setAttrs({ ...attrs, brand: e.target.value ? src(e.target.value) : null })} />
            <datalist id="brands">{tax?.brands.map((b) => <option key={b} value={b} />)}</datalist>
          </Field>
          <div className="field">
            <span className="label">{t("report.colors")}</span>
            <div className="chips">
              {tax?.colors.map((c) => {
                const on = !!attrs.colors?.some((x) => x.value === c.name);
                return (
                  <button key={c.name} type="button" className="chip" aria-pressed={on}
                    onClick={() => setAttrs({ ...attrs, colors: on ? (attrs.colors ?? []).filter((x) => x.value !== c.name) : [...(attrs.colors ?? []), src(c.name)].slice(-2) })}>
                    <span className="swatch" style={{ background: c.hex }} />{c.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="field">
            <span className="label">{t("report.marks")}</span>
            <div className="chips">
              {(attrs.marks ?? []).map((m, i) => (
                <span key={m.value + i} className="chip">
                  {m.value}
                  {!lost && <button type="button" className="lockbtn" aria-pressed={!!m.hidden} onClick={() => setHidden("marks", i, !m.hidden)}><Icon n="lock" size={14} /> {t("report.private")}</button>}
                  <button type="button" className="chip__x" aria-label={`Remove ${m.value}`} onClick={() => setAttrs({ ...attrs, marks: (attrs.marks ?? []).filter((_, j) => j !== i) })}><Icon n="x" size={14} /></button>
                </span>
              ))}
            </div>
            <div className="row">
              <input className="input" value={markDraft} onChange={(e) => setMarkDraft(e.target.value)} placeholder="sticker: crescent moon" list="marks"
                onKeyDown={(e) => { if (e.key === "Enter" && markDraft.trim()) { e.preventDefault(); setAttrs({ ...attrs, marks: [...(attrs.marks ?? []), src(markDraft.trim(), !lost)] }); setMarkDraft(""); } }} />
              <datalist id="marks">{tax?.marks.map((m) => <option key={m} value={m} />)}</datalist>
              <button type="button" className="btn btn--ghost" disabled={!markDraft.trim()} onClick={() => { setAttrs({ ...attrs, marks: [...(attrs.marks ?? []), src(markDraft.trim(), !lost)] }); setMarkDraft(""); }}>{t("report.addMark")}</button>
            </div>
          </div>
          <Field label={t("report.serial")}>
            <div className="row">
              <input className="input" value={attrs.serial?.value ?? ""} onChange={(e) => setAttrs({ ...attrs, serial: e.target.value ? { ...src(e.target.value), hidden: attrs.serial?.hidden ?? (lost ? undefined : true) } : null })} />
              {!lost && attrs.serial && <button type="button" className="lockbtn" aria-pressed={!!attrs.serial.hidden} onClick={() => setHidden("serial", 0, !attrs.serial?.hidden)}><Icon n="lock" size={14} /> {t("report.private")}</button>}
            </div>
          </Field>
          {!lost && <p className="banner banner--orange">{t("report.privateHint")}</p>}
          <div className="row">
            <button className="btn btn--quiet" onClick={() => setStep(1)}>{t("report.back")}</button>
            <button className="btn btn--ink" style={{ flex: 1 }} disabled={reading} onClick={() => setStep(3)}>{t("report.next")}</button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="stack">
          <Field label={t("report.where")}>
            <select className="select" value={zone} onChange={(e) => chooseZone(e.target.value)}><option value="">{t("report.choosePlace")}</option>{zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}</select>
          </Field>
          <PlaceMap
            markers={pin ? [{ id: "pick", kind: "pick", lat: pin.lat, lon: pin.lon, label: lost ? "Lost about here" : "Found about here" }] : []}
            focus={aim}
            onGround={tapMap}
            hint={lost ? "Tap the map to mark exactly where you lost it" : "Tap the map to mark exactly where you found it"}
          />
          <div className="field">
            <span className="label">{lost ? t("report.whenLost") : t("report.whenFound")}</span>
            <div className="chips">
              {(["now", "today", "yesterday", "pick"] as const).map((w) => (
                <button key={w} type="button" className="chip" aria-pressed={whenKey === w} onClick={() => setWhenKey(w)}>{t(`report.${w}` as "report.now")}</button>
              ))}
            </div>
            {whenKey === "pick" && <input className="input" type="datetime-local" max={toLocalInput(new Date())} value={picked} onChange={(e) => setPicked(e.target.value)} />}
          </div>
          {!lost && (
            <Field label={t("report.custody")}>
              <select className="select" value={custody} onChange={(e) => setCustody(e.target.value)}>
                <option value="">{t("report.withMe")}</option>
                {zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            </Field>
          )}
          {err && <p className="err" role="alert">{err}</p>}
          <div className="row">
            <button className="btn btn--quiet" onClick={() => setStep(2)}>{t("report.back")}</button>
            <button className={`btn ${lost ? "btn--lost" : "btn--ink"}`} style={{ flex: 1 }} disabled={busy || !zone} onClick={submit}>{t("report.submit")}{zone ? ` · ${zoneName(zone)}` : ""}</button>
          </div>
        </div>
      )}
    </main>
  );
}
