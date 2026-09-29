import { useEffect, useRef } from "react";

// Small seeded generator so the sky is the same on every load.
const rng = (seed: number) => () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);

function paint(canvas: HTMLCanvasElement, count: number, bright: boolean, seed: number) {
  const dpr = Math.min(devicePixelRatio || 1, 2);
  const w = innerWidth, h = innerHeight;
  canvas.width = w * dpr;
  canvas.height = h * dpr;
  const g = canvas.getContext("2d")!;
  g.scale(dpr, dpr);
  const r = rng(seed);
  for (let i = 0; i < count; i++) {
    const x = r() * w, y = r() * h, m = r();
    const size = bright ? 0.9 + m * 1.1 : 0.4 + m * m * 1.1;
    const tint = m > 0.85 ? "255,214,180" : m < 0.15 ? "190,210,255" : "255,255,255";
    g.fillStyle = `rgba(${tint},${bright ? 0.9 : 0.25 + m * 0.6})`;
    g.beginPath();
    g.arc(x, y, size, 0, Math.PI * 2);
    g.fill();
  }
}

/** Fixed starfield behind the page. Only visible in dark mode (see .stars in global.css). */
export default function Stars() {
  const still = useRef<HTMLCanvasElement>(null);
  const twinkle = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const draw = () => {
      if (still.current) paint(still.current, Math.round((innerWidth * innerHeight) / 2600), false, 7);
      if (twinkle.current) paint(twinkle.current, 60, true, 41);
    };
    draw();
    let t = 0;
    const on = () => { clearTimeout(t); t = window.setTimeout(draw, 150); };
    addEventListener("resize", on);
    return () => { removeEventListener("resize", on); clearTimeout(t); };
  }, []);
  return (
    <div className="stars" aria-hidden="true">
      <canvas ref={still} />
      <canvas ref={twinkle} className="stars__twinkle" />
    </div>
  );
}
