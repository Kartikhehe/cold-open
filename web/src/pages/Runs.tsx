import { Link } from "react-router-dom";
import { usd } from "../lib/format";
import { useApi } from "../lib/hooks";
import type { RunListItem } from "../lib/types";

export function RunsPage() {
  const { data, error } = useApi<RunListItem[]>("/api/runs");
  return (
    <div className="max-w-4xl">
      <h2 className="text-xl font-semibold">Runs</h2>
      <p className="mt-1 text-sm text-fog">Each run reads one show and proposes a launch slate of promos.</p>
      {error && <p className="mt-4 text-rec-ink">{error.message}</p>}
      {data && data.length === 0 && (
        <div className="mt-6 rounded-panel border border-dashed border-rule p-8 text-center">
          <p>No runs yet.</p>
          <Link to="/new" className="mt-3 inline-block rounded-chip bg-tungsten px-4 py-2 text-sm font-semibold text-ink">
            Start a run
          </Link>
        </div>
      )}
      <ul className="mt-6 flex flex-col gap-2">
        {data?.map((r) => (
          <li key={r.id}>
            <Link to={`/run/${r.id}/map`} className="grid gap-2 rounded-panel border border-rule bg-console p-4 transition-colors hover:bg-raised sm:grid-cols-[1fr_auto]">
              <div className="min-w-0">
                <p className="truncate font-semibold">{r.show}</p>
                <p className="font-cond text-xs text-fog">
                  {r.id}, {new Date(r.date).toLocaleString()}
                  {r.models.provider !== "live" ? `, ${r.models.provider} provider` : ""}
                </p>
              </div>
              <div className="flex gap-6 font-cond text-sm tnum">
                <span><span className="text-fog">Promos </span>{r.valid}</span>
                <span><span className="text-fog">Calls </span>{r.llm_calls}</span>
                <span><span className="text-fog">Cost </span>{usd(r.cost_usd)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
