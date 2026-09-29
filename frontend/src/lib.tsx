import { useCallback, useEffect, useRef, useState } from "react";
import { token } from "./api";

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const run = useCallback(() => {
    setLoading(true);
    return fnRef.current().then((d) => { setData(d); setError(null); }).catch((e: Error) => setError(e)).finally(() => setLoading(false));
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void run(); }, deps);
  return { data, error, loading, reload: run, setData };
}

let locale = "en";
export const setLocale = (l: string) => { locale = l; };

export function whenText(iso: string): string {
  const d = new Date(iso);
  if (isNaN(+d)) return "";
  const mins = Math.round((Date.now() - +d) / 60000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  if (mins < 1) return rtf.format(0, "second");
  if (mins < 60) return rtf.format(-mins, "minute");
  if (mins < 60 * 24) return rtf.format(-Math.round(mins / 60), "hour");
  return d.toLocaleDateString(locale, { day: "numeric", month: "short" }) + ", " + d.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

export const nice = (s: string | null | undefined) => (s ?? "").replace(/_/g, " ");

// Private originals need the bearer token, so <img src> can't be used. Fetch and show as a blob.
export function useAuthImage(url: string | undefined): string | null {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!url) return;
    let alive = true, obj: string | null = null;
    fetch(url, { headers: { Authorization: `Bearer ${token.get() ?? ""}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject()))
      .then((b) => { if (alive) { obj = URL.createObjectURL(b); setSrc(obj); } })
      .catch(() => {});
    return () => { alive = false; if (obj) URL.revokeObjectURL(obj); };
  }, [url]);
  return src;
}

export function toLocalInput(d: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
