import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AccessGate } from "./components/AccessGate";
import { NavTabs, RunLayout, TopBar } from "./components/Shell";
import { ToastProvider } from "./components/Toast";
import { getAccessCode, onAuthChange } from "./lib/api";
import { CutRoomPage } from "./pages/CutRoom";
import { MapPage } from "./pages/Map";
import { QualityPage } from "./pages/Quality";
import { RunPage } from "./pages/Run";
import { RunsPage } from "./pages/Runs";
import { SlatePage } from "./pages/Slate";

export function App() {
  const [health, setHealth] = useState<{ access_code_required: boolean } | null>(null);
  const [, force] = useState(0);
  useEffect(() => {
    fetch("/api/health").then((r) => r.json()).then(setHealth).catch(() => setHealth({ access_code_required: false }));
    return onAuthChange(() => force((n) => n + 1));
  }, []);

  if (!health) return null;
  const locked = health.access_code_required && !getAccessCode();

  return (
    <ToastProvider>
      <BrowserRouter>
        {locked ? (
          <Routes>
            <Route path="/new" element={<Standalone><RunPage /></Standalone>} />
            <Route path="*" element={<Standalone><AccessGate /></Standalone>} />
          </Routes>
        ) : (
          <Routes>
            <Route path="/" element={<Standalone><RunsPage /></Standalone>} />
            <Route path="/new" element={<Standalone><RunPage /></Standalone>} />
            <Route path="/run/:runId" element={<RunLayout />}>
              <Route index element={<Navigate to="map" replace />} />
              <Route path="map" element={<MapPage />} />
              <Route path="slate" element={<SlatePage />} />
              <Route path="promo/:pid?" element={<CutRoomPage />} />
              <Route path="quality" element={<QualityPage />} />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </BrowserRouter>
    </ToastProvider>
  );
}

function Standalone({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <TopBar title="Cold Open" />
      <NavTabs />
      <main id="main" className="mx-auto max-w-[1600px] px-4 py-6 md:px-6">{children}</main>
    </>
  );
}
