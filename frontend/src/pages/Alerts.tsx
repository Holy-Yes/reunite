import { useNavigate } from "react-router-dom";
import { api, type Alert } from "../api";
import { useT } from "../i18n";
import { useAsync, whenText } from "../lib";
import { ErrorBox, Loading } from "../components/bits";

// The backend links notifications to the route names in the API docs; map the few that differ here.
export function routeFor(href: string): string {
  return href.replace(/^\/claims\/([^/]+)\/handover$/, "/claims/$1/pass");
}

export default function Alerts({ onRead }: { onRead: () => void }) {
  const { t } = useT();
  const nav = useNavigate();
  const list = useAsync(() => api.alerts(), []);
  async function open(a: Alert) {
    if (!a.read) { await api.readAlert(a.id).catch(() => {}); onRead(); }
    nav(routeFor(a.href));
  }
  return (
    <main className="page stack--lg stack" id="main">
      <div className="row row--between">
        <h1 className="h2">{t("alerts.title")}</h1>
        {!!list.data?.some((a) => !a.read) && <button className="btn btn--quiet" onClick={async () => { await api.readAll(); await list.reload(); onRead(); }}>{t("alerts.readAll")}</button>}
      </div>
      {list.loading && !list.data ? <Loading /> : list.error ? <ErrorBox error={list.error} retry={list.reload} /> : !list.data?.length ? <p className="empty">{t("alerts.empty")}</p> : (
        <ul className="list">
          {list.data.map((a) => (
            <li key={a.id}>
              <button className="li" style={{ width: "100%", textAlign: "left" }} onClick={() => open(a)}>
                <span className="li__body"><strong style={{ fontWeight: a.read ? 400 : 600 }}>{a.title}</strong><span>{a.body} · {whenText(a.at)}</span></span>
                {!a.read && <span className="tag tag--lost">new</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
