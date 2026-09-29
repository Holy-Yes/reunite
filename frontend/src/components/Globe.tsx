import { useEffect, useRef, useState } from "react";
import type { GlobeApi } from "../globe/globe";
import { useTheme } from "../theme";

type Props = {
  onReady(api: GlobeApi): void;
  onHover(index: number | null, x: number, y: number): void;
};

/** Hosts the three.js globe. It loads on idle so the page paints first; if it fails, the static SVG stays. */
export default function Globe({ onReady, onHover }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<GlobeApi | null>(null);
  const { theme } = useTheme();
  const themeNow = useRef(theme);
  themeNow.current = theme;
  const cb = useRef({ onReady, onHover });
  cb.current = { onReady, onHover };
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");

  useEffect(() => {
    if (new URLSearchParams(location.search).has("noglobe")) {
      setState("failed");
      return;
    }
    let made: GlobeApi | null = null;
    let dead = false;
    const boot = async () => {
      try {
        const { createGlobe } = await import("../globe/globe");
        if (dead || !host.current) return;
        made = await createGlobe({
          host: host.current,
          theme: themeNow.current,
          onHover: (i, x, y) => cb.current.onHover(i, x, y),
        });
        if (dead) return made.destroy();
        api.current = made;
        if (import.meta.env.DEV) (window as unknown as { __globe: GlobeApi }).__globe = made;
        setState("ready");
        cb.current.onReady(made);
      } catch (err) {
        console.error("Globe failed to start, showing the static fallback.", err);
        if (!dead) setState("failed");
      }
    };
    const idle = "requestIdleCallback" in window;
    const id: number = idle ? window.requestIdleCallback(boot) : window.setTimeout(boot, 200);
    return () => {
      dead = true;
      if (idle) window.cancelIdleCallback(id);
      else clearTimeout(id);
      api.current = null;
      made?.destroy();
    };
  }, []);

  useEffect(() => api.current?.setTheme(theme), [theme]);

  return (
    <>
    <div className={`globe-wrap globe-${state}`} id="globe-wrap">
      <div
        className="globe"
        ref={host}
        role="img"
        aria-label="Interactive globe showing lost and found reports. Drag to spin it, scroll to zoom."
      />
      <svg className="globe-fallback" viewBox="0 0 400 400" aria-hidden="true">
        <circle cx="200" cy="200" r="198" fill="var(--surface-2)" stroke="var(--ink)" strokeOpacity=".18" />
        <ellipse cx="200" cy="200" rx="80" ry="198" fill="none" stroke="var(--ink)" strokeOpacity=".15" />
        <ellipse cx="200" cy="200" rx="150" ry="198" fill="none" stroke="var(--ink)" strokeOpacity=".15" />
        <path d="M2 200h396M20 130h360M20 270h360" stroke="var(--ink)" strokeOpacity=".15" fill="none" />
        <circle cx="262" cy="150" r="7" fill="#FF6A13" />
        <circle cx="140" cy="250" r="5" fill="var(--ink)" />
      </svg>
    </div>
    </>
  );
}
