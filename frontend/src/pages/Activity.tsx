import { Link } from "react-router-dom";
import { api, type Claim } from "../api";
import { useT } from "../i18n";
import { nice, useAsync, whenText } from "../lib";
import { ErrorBox, Loading } from "../components/bits";

function Row({ c }: { c: Claim }) {
  const tone = ["approved", "auto_approved", "handed_over"].includes(c.status) ? "tag--ok" : c.status === "rejected" ? "tag--bad" : "";
  return (
    <li>
      <Link to={`/claims/${c.id}`} className="li">
        <span className="li__body"><strong style={{ textTransform: "capitalize" }}>{[c.item.colors[0], c.item.brand, nice(c.item.category)].filter(Boolean).join(" ")}</strong><span>{c.item.ticket_no} · {whenText(c.created_at)}</span></span>
        <span className={`tag ${tone}`}>{nice(c.status)}</span>
      </Link>
    </li>
  );
}

export default function Activity() {
  const { t } = useT();
  const theirs = useAsync(() => api.claims("finder"), []);
  const mine = useAsync(() => api.claims("claimant"), []);
  const err = theirs.error ?? mine.error;
  return (
    <main className="page stack--lg stack" id="main">
      <h1 className="h2">{t("nav.activity")}</h1>
      {err && <ErrorBox error={err} retry={() => { void theirs.reload(); void mine.reload(); }} />}
      {(theirs.loading && !theirs.data) || (mine.loading && !mine.data) ? <Loading /> : (
        <>
          <section className="stack" aria-labelledby="a1">
            <h2 className="h3" id="a1">{t("claim.review")}</h2>
            {theirs.data?.length ? <ul className="list">{theirs.data.map((c) => <Row key={c.id} c={c} />)}</ul> : <p className="empty">{t("desk.empty")}</p>}
          </section>
          <section className="stack" aria-labelledby="a2">
            <h2 className="h3" id="a2">{t("claim.title")}</h2>
            {mine.data?.length ? <ul className="list">{mine.data.map((c) => <Row key={c.id} c={c} />)}</ul> : <p className="empty">{t("desk.empty")}</p>}
          </section>
        </>
      )}
    </main>
  );
}
