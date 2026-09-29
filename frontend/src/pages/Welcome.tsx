import { useCallback, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Globe from "../components/Globe";
import Brand from "../components/Brand";
import ThemeToggle from "../components/ThemeToggle";
import { useAuth } from "../auth";
import { Icon, IconSprite } from "../components/Icons";
import { vnr } from "../globe/config";
import type { GlobeApi } from "../globe/globe";

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

type Tip = { x: number; y: number; title: string; sub: string } | null;

export default function Welcome() {
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const globe = useRef<GlobeApi | null>(null);
  const hero = useRef<HTMLElement>(null);
  const [tip, setTip] = useState<Tip>(null);
  const [launching, setLaunching] = useState(false);
  const [fade, setFade] = useState(false);

  // The only marker you can point at is the campus itself.
  const hover = useCallback((index: number | null, x: number, y: number) => {
    if (index === null) return setTip(null);
    const box = hero.current!.getBoundingClientRect();
    const wrap = document.getElementById("globe-wrap")!.getBoundingClientRect();
    setTip({ x: wrap.left - box.left + x + 14, y: wrap.top - box.top + y + 14, title: vnr.name, sub: `${vnr.place} · your campus` });
  }, []);

  // Log in and Report an item: spin the globe very fast, land on VNR VJIET, then open the campus map.
  const launch = async (next: string) => {
    if (launching) return;
    setLaunching(true);
    setTip(null);
    const map = import("./Campus").catch(() => undefined); // load Cesium while the globe spins
    await globe.current?.launchToCampus();
    await map;
    setFade(true);
    await sleep(reduced() ? 0 : 340);
    navigate(`/campus?next=${encodeURIComponent(next)}`, { state: { dive: true } });
  };

  return (
    <>
      <IconSprite />
      <div className={`fade${fade ? " fade--on" : ""}`} aria-hidden="true" />

      <header className="nav">
        <a className="brand" href="#top" aria-label="reunite, home">
          <Brand />
        </a>
        <nav className="nav__links" aria-label="Main">
                    <a href="#how">How it works</a>
          <a href="#desk">For the desk</a>
        </nav>
        {user ? (
          <>
            <Link className="nav__login" to="/home">Open app</Link>
            <span className="nav__user mono" title={user.email}>{user.email}</span>
            <button className="nav__login" type="button" onClick={signOut}>Sign out</button>
          </>
        ) : (
          <button className="nav__login" type="button" disabled={launching} onClick={() => launch("/signin")}>Log in</button>
        )}
        <button className="nav__cta" type="button" disabled={launching} aria-busy={launching} onClick={() => launch("/report/lost")}>
          Report an item <Icon name="up-right" />
        </button>
        <ThemeToggle />
      </header>

      <main id="top">
        <section className="hero" aria-labelledby="headline" ref={hero}>
          <Globe onReady={(api) => (globe.current = api)} onHover={hover} />

          {tip && (
            <div className="tip tip--campus" role="status" style={{ transform: `translate(${tip.x}px, ${tip.y}px)` }}>
              <strong>{tip.title}</strong>
              <span>{tip.sub}</span>
            </div>
          )}

          <div className="hero__copy">
            <p className="eyebrow"><Icon name="star" size={12} /> A shorter way home</p>
            <h1 id="headline">What's missing can find its <em>way back.</em></h1>
            <p className="lede">A calmer path from the moment you lose something to the moment it is safely handed back.</p>
            <div className="actions">
              <button className="btn btn--lost" type="button" disabled={launching} onClick={() => launch("/report/lost")}>
                Start a report <Icon name="up-right" size={18} />
              </button>
              <a className="textlink" href="#how">See how it works <Icon name="down" /></a>
            </div>
          </div>

          <p className="edge">Campus lost + found <span aria-hidden="true">&nbsp;/&nbsp;</span> Est. 2026</p>
        </section>

        <section className="how" id="how" aria-labelledby="how-h">
          <div className="how__head">
            <p className="eyebrow"><Icon name="star" size={12} /> The handoff, made clear</p>
            <h2 id="how-h">Three small steps.<br /><em>One less thing to carry.</em></h2>
          </div>
          <ol className="how__steps" role="list">
            <li><span className="mono">01</span><h3>Tell us what happened.</h3><p>Describe it in a few words or add a photo. Keep moving; your draft stays on this phone.</p></li>
            <li><span className="mono">02</span><h3>See why it matches.</h3><p>We line up the useful details and show you the best candidate in plain language.</p></li>
            <li><span className="mono">03</span><h3>Hand it back safely.</h3><p>A verified claim and a simple QR handover keep the final exchange clear.</p></li>
          </ol>
        </section>

        <section className="desk" id="desk" aria-labelledby="desk-h">
          <div>
            <p className="eyebrow"><Icon name="star" size={12} /> For the people at the desk</p>
            <h2 id="desk-h">More context<br /><em>when it matters.</em></h2>
          </div>
          <p className="desk__copy">A calmer claims queue, clearer handovers, and a campus-wide picture of what is moving.</p>
          <a className="btn btn--ghost" href="#desk">Explore the desk view <Icon name="up-right" size={18} /></a>
        </section>
      </main>

      <footer className="foot">
        <a className="brand" href="#top" aria-label="reunite, top"><Brand size={26} /></a>
        <p>Items only · Privacy first · Made for campus</p>
        <p className="foot__right">Globe: three.js, Natural Earth · © 2026</p>
      </footer>
    </>
  );
}
