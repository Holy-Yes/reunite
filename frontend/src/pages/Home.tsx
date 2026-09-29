import { Link } from "react-router-dom";
import { api, type Item } from "../api";
import { useAuth } from "../auth";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { nice, useAsync, whenText } from "../lib";
import { useRef_ } from "../ref";
import { ErrorBox, Loading, StatusTag, Thumb } from "../components/bits";

function label(i: Item) {
  const a = i.attributes;
  return [a.colors?.[0]?.value, a.brand?.value, nice(a.category?.value) || i.description.slice(0, 40)].filter(Boolean).join(" ");
}

export default function Home() {
  const { t } = useT();
  const { user } = useAuth();
  const { zoneName } = useRef_();
  const items = useAsync(() => api.items(), []);
  const matches = useAsync(() => api.matches(), []);
  const found = useAsync(() => api.publicItems(), []);
  const pending = matches.data?.length ?? 0;

  return (
    <main className="page stack--lg stack" id="main">
      <div className="stack">
        <p className="eyebrow eyebrow--quiet">{user?.email}</p>
        <h1 className="h1">{t("home.title")}</h1>
      </div>

      <div className="stack">
        <Link to="/report/lost" className="big big--lost"><div><strong>{t("home.lost")}</strong><span>{t("home.lostHint")}</span></div><Icon n="up" size={28} /></Link>
        <Link to="/report/found" className="big big--found"><div><strong>{t("home.found")}</strong><span>{t("home.foundHint")}</span></div><Icon n="up" size={28} /></Link>
      </div>

      {pending > 0 && (
        <Link to="/matches" className="callout"><span>{pending} {t("home.matchesWaiting")}</span><Icon n="up" /></Link>
      )}

      <section className="stack" aria-labelledby="mine-h">
        <h2 className="h3" id="mine-h">{t("home.mine")}</h2>
        {items.loading && !items.data ? <Loading /> : items.error ? <ErrorBox error={items.error} retry={items.reload} /> : !items.data?.length ? (
          <p className="empty">{t("home.none")}</p>
        ) : (
          <ul className="list">
            {items.data.map((i) => (
              <li key={i.id}>
                <Link to={`/items/${i.id}`} className="li">
                  <Thumb url={i.photos[0]?.url} priv alt="" />
                  <span className="li__body"><strong>{label(i)}</strong><span>{i.ticket_no} · {zoneName(i.zone_id)} · {whenText(i.created_at)}</span></span>
                  <span className="stack--sm stack" style={{ alignItems: "flex-end" }}>
                    <span className={`tag ${i.kind === "lost" ? "tag--lost" : "tag--ink"}`}>{t(`kind.${i.kind}` as "kind.lost")}</span>
                    <StatusTag status={i.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {!!found.data?.length && (
        <section className="stack" aria-labelledby="browse-h">
          <h2 className="h3" id="browse-h">{t("home.browse")}</h2>
          <ul className="list">
            {found.data.slice(0, 5).map((f) => (
              <li key={f.id} className="li">
                <Thumb url={f.photo?.url} alt="" />
                <span className="li__body"><strong>{[f.colors[0], f.brand, nice(f.category)].filter(Boolean).join(" ")}</strong><span>{zoneName(f.zone_id)} · {whenText(f.found_at)}</span></span>
                <span className="tag">{t("common.private")}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
