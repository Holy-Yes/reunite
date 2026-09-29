import { Link, useParams } from "react-router-dom";
import PlaceMap from "../components/PlaceMap";
import { api, ApiError } from "../api";
import { useT } from "../i18n";
import { nice, useAsync, useAuthImage, whenText } from "../lib";
import { useRef_ } from "../ref";
import { ErrorBox, Loading, StatusTag } from "../components/bits";
import { useState } from "react";

function Photo({ url }: { url: string }) {
  const src = useAuthImage(url);
  return src ? <img src={src} alt="" style={{ borderRadius: "var(--r-2)", maxHeight: 320, objectFit: "cover" }} /> : null;
}

export default function ItemPage() {
  const { id = "" } = useParams();
  const { t } = useT();
  const { zoneName, zones } = useRef_();
  const item = useAsync(() => api.item(id), [id]);
  const ev = useAsync(() => api.events(id), [id]);
  const [err, setErr] = useState("");
  const i = item.data;
  if (item.loading && !i) return <main className="page" id="main"><Loading /></main>;
  if (item.error || !i) return <main className="page" id="main"><ErrorBox error={item.error ?? new Error("Not found")} retry={item.reload} /></main>;
  const a = i.attributes;
  const heldAt = (zid: string) => {
    const z = zones.find((q) => q.id === zid);
    return z?.centroid ? [{ id: "held", kind: "collect" as const, lat: z.centroid[1], lon: z.centroid[0], label: `Held at ${z.name}` }] : [];
  };
  const open = !["closed", "returned"].includes(i.status);
  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack--sm stack">
        <div className="row"><span className={`tag ${i.kind === "lost" ? "tag--lost" : "tag--ink"}`}>{t(`kind.${i.kind}` as "kind.lost")}</span><StatusTag status={i.status} /></div>
        <h1 className="h2" style={{ textTransform: "capitalize" }}>{[a.colors?.[0]?.value, a.brand?.value, nice(a.category?.value)].filter(Boolean).join(" ") || i.ticket_no}</h1>
        <p className="muted mono">{i.ticket_no}</p>
      </div>
      {i.routed_to && <p className="banner banner--orange">{t("common.routed")} {i.routed_to}</p>}
      {i.photos.map((p) => <Photo key={p.id} url={p.url} />)}
      {i.description && <p>{i.description}</p>}
      <dl className="review">
        <div><dt>{t("report.where")}</dt><dd>{zoneName(i.zone_id)}</dd></div>
        <div><dt>{t("report.when")}</dt><dd>{whenText(i.occurred_from)}</dd></div>
        {!!a.marks?.length && <div><dt>{t("report.marks")}</dt><dd>{a.marks.map((m) => m.value + (m.hidden ? ` (${t("common.private")})` : "")).join(", ")}</dd></div>}
        {a.serial && <div><dt>{t("report.serial")}</dt><dd>{a.serial.value}{a.serial.hidden ? ` (${t("common.private")})` : ""}</dd></div>}
      </dl>
      {i.lat != null && i.lon != null && (
        <section className="stack--sm stack" aria-label="On the map">
          <PlaceMap
            markers={[
              { id: "here", kind: i.kind, lat: i.lat, lon: i.lon, label: i.kind === "lost" ? "Lost here" : "Found here" },
              ...(i.kind === "found" && i.custody_zone_id ? heldAt(i.custody_zone_id) : []),
            ]}
            focus={{ lat: i.lat, lon: i.lon }}
            height={260}
          />
        </section>
      )}
      {i.kind === "lost" && i.match_count > 0 && open && <Link className="btn btn--lost" to={`/matches?item=${i.id}`}>{t("matches.title")} · {i.match_count}</Link>}
      <section className="stack" aria-labelledby="tl">
        <h2 className="h3" id="tl">{t("item.timeline")}</h2>
        <ol className="timeline">{ev.data?.map((e) => <li key={e.id}><b>{nice(e.type)}</b> <span className="muted">· {whenText(e.at)}</span>{e.note && <div className="muted">{e.note}</div>}</li>)}</ol>
      </section>
      {err && <p className="err">{err}</p>}
      {open && <button className="btn btn--quiet" onClick={async () => { try { await api.closeItem(i.id); await item.reload(); await ev.reload(); } catch (x) { setErr((x as ApiError).message); } }}>{t("item.close")}</button>}
    </main>
  );
}
