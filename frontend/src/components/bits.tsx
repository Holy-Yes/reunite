import type { ReactNode } from "react";
import { useT, type Key } from "../i18n";
import type { Band, Trust } from "../api";
import { nice, useAuthImage } from "../lib";
import { Icon } from "../icons";

export function Loading() {
  const { t } = useT();
  return <p className="muted row" role="status"><span className="spin" /> {t("common.loading")}</p>;
}

export function ErrorBox({ error, retry }: { error: Error; retry?: () => void }) {
  const { t } = useT();
  return (
    <div className="banner banner--bad stack--sm stack" role="alert">
      <span>{error.message}</span>
      {retry && <button className="btn btn--ghost" onClick={retry}>{t("common.retry")}</button>}
    </div>
  );
}

export function StatusTag({ status }: { status: string }) {
  const { t } = useT();
  const tone = status === "returned" ? "tag--ok" : status === "closed" ? "" : status === "matched" ? "tag--ink" : "";
  return <span className={`tag ${tone}`}>{t(`status.${status}` as Key) === `status.${status}` ? nice(status) : t(`status.${status}` as Key)}</span>;
}

export function BandTag({ band }: { band: Band }) {
  const { t } = useT();
  return <span className={`tag ${band === "strong" ? "tag--ok" : band === "possible" ? "tag--lost" : ""}`}>{t(`band.${band}` as Key)}</span>;
}

export function TrustBadge({ trust }: { trust: Trust }) {
  const { t } = useT();
  return (
    <span className="trust" data-level={trust.level} title={`${trust.items_returned} ${t("trust.returned")} · ${trust.claims_approved} ${t("trust.approved")}`}>
      <span className="trust__bar" aria-hidden="true"><i style={{ width: `${trust.score}%` }} /></span>
      <span>{t(`trust.${trust.level}` as Key)}</span>
    </span>
  );
}

export function Thumb({ url, priv, alt = "" }: { url?: string; priv?: boolean; alt?: string }) {
  return priv ? <PrivateImg url={url} alt={alt} /> : url ? <img className="li__thumb" src={url} alt={alt} loading="lazy" /> : <span className="li__thumb"><Icon n="image" /></span>;
}
function PrivateImg({ url, alt }: { url?: string; alt: string }) {
  const src = useAuthImage(url);
  return src ? <img className="li__thumb" src={src} alt={alt} /> : <span className="li__thumb"><Icon n="image" /></span>;
}

export function Field({ label, children, error }: { label: string; children: ReactNode; error?: string }) {
  return (
    <label className="field">
      <span className="label">{label}</span>
      {children}
      {error && <span className="err">{error}</span>}
    </label>
  );
}
