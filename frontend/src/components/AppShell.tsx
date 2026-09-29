import { useCallback, useEffect } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { LANGS, useT } from "../i18n";
import { Icon } from "../icons";
import { useAsync } from "../lib";
import { RefProvider } from "../ref";
import Brand from "./Brand";
import ThemeToggle from "./ThemeToggle";

/** The signed-in app: top bar, tabs, and the pages inside. Signed-out visitors go to sign in and come back. */
export default function AppShell() {
  const { t, lang, setLang } = useT();
  const { user, ready, signOut } = useAuth();
  const loc = useLocation();
  const alerts = useAsync(() => (user ? api.alerts() : Promise.resolve([])), [user?.id]);
  const unread = alerts.data?.filter((a) => !a.read).length ?? 0;
  const refreshAlerts = useCallback(() => void alerts.reload(), [alerts]);

  useEffect(() => {
    if (!user) return;
    const id = window.setInterval(() => void alerts.reload(), 30_000);
    return () => clearInterval(id);
  }, [user, alerts]);

  if (!ready) return <div className="app" />;
  if (!user) return <Navigate to={`/signin?then=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;

  const tabs = [
    { to: "/home", icon: "home", label: t("nav.home") },
    { to: "/matches", icon: "match", label: t("nav.matches") },
    { to: "/activity", icon: "activity", label: t("nav.activity") },
    { to: "/campus?next=%2Freport%2Flost", icon: "pin", label: "Map" },
    { to: "/alerts", icon: "bell", label: t("nav.alerts"), dot: unread },
    { to: "/me", icon: "user", label: t("nav.me") },
    ...(user.role === "security_guard" ? [{ to: "/guard", icon: "desk", label: t("nav.guard") }] : user.role !== "student" ? [{ to: "/desk", icon: "desk", label: t("nav.desk") }] : []),
  ];

  return (
    <RefProvider>
      <div className="app">
        <a className="skip" href="#main">Skip to content</a>
        <header className="top">
          <Link className="brand" to="/home" aria-label="reunite, home"><Brand size={28} /></Link>
          <nav className="tabs" aria-label="Main">
            {tabs.map((x) => (
              <NavLink key={x.to} to={x.to} className="tab" aria-current={loc.pathname === x.to.split("?")[0] ? "page" : undefined}>
                <Icon n={x.icon} size={22} />
                <span>{x.label}</span>
                {!!x.dot && <span className="tab__dot" aria-label={`${x.dot} unread`}>{x.dot}</span>}
              </NavLink>
            ))}
          </nav>
          <div className="top__end">
            <div className="lang" role="group" aria-label="Language">
              {LANGS.map((l) => (
                <button key={l.id} type="button" aria-pressed={l.id === lang} onClick={() => setLang(l.id)}>{l.label}</button>
              ))}
            </div>
            <ThemeToggle />
            <button className="btn btn--quiet" type="button" onClick={signOut}>Sign out</button>
          </div>
        </header>
        <Outlet context={{ refreshAlerts }} />
      </div>
    </RefProvider>
  );
}
