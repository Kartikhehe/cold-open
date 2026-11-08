import { createContext, useContext, type ReactNode } from "react";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { getAccessCode } from "../lib/api";
import { usd } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { ShowResp, SlateResp } from "../lib/types";

type RunCtx = { runId: string; show: ShowResp; slate: SlateResp; reloadSlate: () => void };
const Ctx = createContext<RunCtx | null>(null);
export const useRun = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("useRun outside a run");
  return c;
};

function Lock() {
  return (
    <svg aria-hidden width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="7" width="10" height="7" rx="1.5" />
      <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
    </svg>
  );
}

function Meta({ label, children, wide = false }: { label: string; children: ReactNode; wide?: boolean }) {
  return (
    <div className={`flex-col ${wide ? "hidden md:flex" : "flex"}`}>
      <span className="font-cond text-xs text-fog">{label}</span>
      <span className="font-cond text-sm tnum">{children}</span>
    </div>
  );
}

export function TopBar({ title, show }: { title: string; show?: ShowResp }) {
  const r = show?.report;
  const secs = r ? Object.values(r.stage_seconds).reduce((a, b) => a + b, 0) : 0;
  return (
    <header className="border-b border-rule">
      <div className="mx-auto flex max-w-[1600px] flex-wrap items-end justify-between gap-x-8 gap-y-3 px-4 pb-3 pt-4 md:px-6">
        <div className="min-w-0">
          <Link to="/" className="font-cond text-xs text-fog hover:text-bone">Cold Open</Link>
          <h1 className="truncate text-lg font-semibold">{title}</h1>
        </div>
        {r && (
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <Meta label="Run">{new Date(r.finished_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</Meta>
            <Meta wide label="Miner">{r.models.miner}</Meta>
            <Meta wide label="Cold Viewer">{r.models.judge}</Meta>
            <Meta wide label="Classifier">{r.models.classifier}</Meta>
            <Meta label="Cost">{usd(r.cost_usd)}</Meta>
            <Meta label="Duration">{secs < 90 ? `${secs.toFixed(0)} s` : `${(secs / 60).toFixed(1)} min`}</Meta>
            {r.models.provider !== "live" && (
              <span className="rounded-chip border border-tungsten/60 px-2 py-0.5 font-cond text-xs text-tungsten">
                {r.models.provider === "mock" ? "Mock run: heuristic stand-ins" : "Replayed from cache"}
              </span>
            )}
            {getAccessCode() && (
              <span className="flex items-center gap-1 text-fog" title="Demo data, unlocked with an access code">
                <Lock />
                <span className="sr-only">Demo data unlocked with an access code</span>
              </span>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

export function NavTabs({ runId, hero }: { runId?: string; hero?: string }) {
  const tabs = runId
    ? [
        { to: `/run/${runId}/map`, label: "Map" },
        { to: `/run/${runId}/slate`, label: "Slate" },
        { to: `/run/${runId}/promo/${hero ?? ""}`, label: "Cut room", match: `/run/${runId}/promo` },
        { to: `/run/${runId}/quality`, label: "Quality" },
        { to: `/new`, label: "Run" },
      ]
    : [{ to: "/", label: "Runs" }, { to: "/new", label: "Run" }];
  return (
    <nav aria-label="Primary" className="border-b border-rule">
      <ul className="mx-auto flex max-w-[1600px] gap-1 overflow-x-auto px-2 md:px-4">
        {tabs.map((t) => (
          <li key={t.label}>
            <NavLink
              to={t.to}
              className={({ isActive }) => {
                const active = isActive || (t.match && location.pathname.startsWith(t.match));
                return `relative block px-3 py-2.5 text-sm transition-colors ${active ? "text-bone after:absolute after:inset-x-3 after:-bottom-px after:h-0.5 after:bg-tungsten" : "text-fog hover:text-bone"}`;
              }}
            >
              {t.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export function RunLayout() {
  const { runId = "" } = useParams();
  const show = useApi<ShowResp>(`/api/runs/${runId}/show`);
  const slate = useApi<SlateResp>(`/api/runs/${runId}/slate`);
  const err = show.error || slate.error;
  return (
    <>
      <a href="#main" className="skip-link">Skip to content</a>
      <TopBar title={show.data?.title ?? (err ? "Run unavailable" : "Loading run…")} show={show.data} />
      <NavTabs runId={runId} hero={slate.data?.slate.hero} />
      <main id="main" className="mx-auto max-w-[1600px] px-4 py-6 md:px-6">
        {err ? (
          <div className="rounded-panel border border-rule bg-console p-6">
            <p className="font-semibold">This run could not be loaded.</p>
            <p className="mt-1 text-sm text-fog">{err.message}</p>
            <Link to="/" className="mt-4 inline-block text-sm text-tungsten underline underline-offset-4">Back to all runs</Link>
          </div>
        ) : show.data && slate.data ? (
          <Ctx.Provider value={{ runId, show: show.data, slate: slate.data, reloadSlate: slate.reload }}>
            <Outlet />
          </Ctx.Provider>
        ) : (
          <MapSkeleton />
        )}
      </main>
    </>
  );
}

function MapSkeleton() {
  return (
    <div aria-busy className="grid gap-6 lg:grid-cols-12">
      <div className="hidden h-[640px] rounded-panel bg-console/60 lg:col-span-3 lg:block" />
      <div className="h-[640px] rounded-panel bg-console/60 lg:col-span-6" />
      <div className="hidden h-[640px] rounded-panel bg-console/60 lg:col-span-3 lg:block" />
    </div>
  );
}
