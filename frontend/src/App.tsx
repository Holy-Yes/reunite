import { lazy, Suspense } from "react";
import { Navigate, Route, Routes, useOutletContext } from "react-router-dom";
import AppShell from "./components/AppShell";
import Welcome from "./pages/Welcome";
import SignIn from "./pages/SignIn";
import Home from "./pages/Home";
import Report from "./pages/Report";
import ItemPage from "./pages/ItemPage";
import Matches from "./pages/Matches";
import Activity from "./pages/Activity";
import Alerts from "./pages/Alerts";
import Me from "./pages/Me";
import ClaimPage from "./pages/Claim";
import Pass from "./pages/Pass";
import Chat from "./pages/Chat";
import Desk from "./pages/Desk";
import Guard from "./pages/Guard";
import Tags from "./pages/Tags";
import PublicTag from "./pages/PublicTag";
import "./styles/app.css";

// Cesium is heavy: it only loads with the campus route.
const Campus = lazy(() => import("./pages/Campus"));

function AlertsRoute() {
  const { refreshAlerts } = useOutletContext<{ refreshAlerts: () => void }>();
  return <Alerts onRead={refreshAlerts} />;
}

export default function App() {
  return (
    <Suspense fallback={null}>
      <Routes>
        <Route path="/" element={<Welcome />} />
        <Route path="/welcome" element={<Welcome />} />
        <Route path="/campus" element={<Campus />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/t/:code" element={<PublicTag />} />

        <Route element={<AppShell />}>
          <Route path="/home" element={<Home />} />
          <Route path="/report/:kind" element={<Report />} />
          <Route path="/items/:id" element={<ItemPage />} />
          <Route path="/matches" element={<Matches />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/alerts" element={<AlertsRoute />} />
          <Route path="/me" element={<Me />} />
          <Route path="/claims/:id" element={<ClaimPage />} />
          <Route path="/claims/:id/pass" element={<Pass />} />
          <Route path="/claims/:id/chat" element={<Chat />} />
          <Route path="/desk" element={<Desk />} />
          <Route path="/guard" element={<Guard />} />
          <Route path="/tags" element={<Tags />} />
        </Route>

        <Route path="*" element={<Navigate to="/welcome" replace />} />
      </Routes>
    </Suspense>
  );
}
