import { sectors } from "./config";
import type { GlobeApi } from "./globe";

const $ = <T extends HTMLElement>(sel: string) => document.querySelector<T>(sel)!;

const name = $("#sector-name");
const meta = $("#sector-meta");
const coords = $("#sector-coords");
const counter = $("#counter");
const overviewBtn = $<HTMLButtonElement>("#overview");
const tip = $("#tip");
const cards = [...document.querySelectorAll<HTMLButtonElement>(".loc")];
const hero = $(".hero");

let globe: GlobeApi | null = null;
let current = 0;
let zoomed = false;

const fmt = (n: number, pos: string, neg: string) => `${Math.abs(n).toFixed(4)}° ${n >= 0 ? pos : neg}`;

function show(index: number) {
  current = index;
  const s = sectors[index];
  name.textContent = s.name;
  meta.textContent = "Campus sector · Live";
  coords.textContent = `${fmt(s.lat, "N", "S")} · ${fmt(s.lon, "E", "W")}`;
  counter.textContent = `${String(index + 1).padStart(2, "0")} / ${String(sectors.length).padStart(2, "0")}`;
  cards.forEach((c, i) => c.setAttribute("aria-pressed", String(i === index)));
}

function choose(index: number) {
  show(index);
  zoomed = true;
  overviewBtn.hidden = false;
  globe?.select(index);
}

function backToEarth() {
  zoomed = false;
  overviewBtn.hidden = true;
  globe?.overview();
}

cards.forEach((c, i) => c.addEventListener("click", () => choose(i)));
overviewBtn.addEventListener("click", backToEarth);
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && zoomed) backToEarth();
});

function hover(index: number | null, x: number, y: number) {
  if (index === null) {
    tip.hidden = true;
    return;
  }
  const s = sectors[index];
  const box = hero.getBoundingClientRect();
  const wrap = $("#globe-wrap").getBoundingClientRect();
  tip.innerHTML = `<strong>${s.name}</strong><span>${s.item} · ${String(s.open).padStart(2, "0")} open</span>`;
  tip.style.transform = `translate(${wrap.left - box.left + x + 14}px, ${wrap.top - box.top + y + 14}px)`;
  tip.hidden = false;
}

async function boot() {
  try {
    const { createGlobe } = await import("./globe");
    globe = await createGlobe({ host: $("#globe"), onSelect: choose, onHover: hover });
    document.body.classList.add("globe-ready");
  } catch (err) {
    console.error("Globe failed to start, showing the static fallback.", err);
    document.body.classList.add("globe-failed");
  }
}

show(0);
// The globe is heavy: let the page paint first, then load it.
if (!new URLSearchParams(location.search).has("noglobe")) {
  "requestIdleCallback" in window ? requestIdleCallback(boot) : setTimeout(boot, 200);
}
