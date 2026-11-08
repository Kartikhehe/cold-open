import * as Menu from "@radix-ui/react-dropdown-menu";
import { useState } from "react";
import { useKeys } from "../lib/hooks";

export const REJECT_REASONS = ["Weak hook", "Confusing", "Spoiler", "Policy", "Duplicate", "Bad cut"];
type Action = "approve_paid" | "organic_only" | "reject";

/** Approve / organic / reject, with keyboard a, o, r. The editor makes the final call. */
export function DecisionBar({
  onDecide,
  blocked,
  exportHref,
  current,
}: {
  onDecide: (a: Action, reason?: string) => void;
  blocked: string | null;
  exportHref: string;
  current?: Action;
}) {
  const [open, setOpen] = useState(false);
  useKeys(
    {
      a: () => !blocked && onDecide("approve_paid"),
      o: () => !blocked && onDecide("organic_only"),
      r: () => setOpen(true),
    },
    [blocked, onDecide],
  );
  const ring = (a: Action) => (current === a ? "ring-2 ring-bone/70 ring-offset-2 ring-offset-console" : "");
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => onDecide("approve_paid")}
          disabled={!!blocked}
          className={`rounded-chip bg-teal px-4 py-2 text-sm font-semibold text-ink transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 ${ring("approve_paid")}`}
        >
          Approve for paid <kbd className="ml-1 font-cond text-xs opacity-70">a</kbd>
        </button>
        <button
          onClick={() => onDecide("organic_only")}
          disabled={!!blocked}
          className={`rounded-chip border border-tungsten px-4 py-2 text-sm text-tungsten transition-colors hover:bg-tungsten/10 disabled:cursor-not-allowed disabled:opacity-40 ${ring("organic_only")}`}
        >
          Organic only <kbd className="ml-1 font-cond text-xs opacity-70">o</kbd>
        </button>
        <Menu.Root open={open} onOpenChange={setOpen}>
          <Menu.Trigger
            className={`rounded-chip border border-rec px-4 py-2 text-sm text-rec-ink transition-colors hover:bg-rec/10 ${ring("reject")}`}
          >
            Reject… <kbd className="ml-1 font-cond text-xs opacity-70">r</kbd>
          </Menu.Trigger>
          <Menu.Portal>
            <Menu.Content sideOffset={6} align="start" className="z-50 min-w-[12rem] rounded-panel border border-rule bg-console p-1 text-sm">
              <Menu.Label className="px-2 py-1 text-xs text-fog">Why reject it?</Menu.Label>
              {REJECT_REASONS.map((r) => (
                <Menu.Item
                  key={r}
                  onSelect={() => onDecide("reject", r.toLowerCase())}
                  className="cursor-pointer rounded-chip px-2 py-1.5 outline-none data-[highlighted]:bg-raised"
                >
                  {r}
                </Menu.Item>
              ))}
            </Menu.Content>
          </Menu.Portal>
        </Menu.Root>
        <a href={exportHref} download className="ml-auto rounded-chip border border-rule px-4 py-2 text-sm hover:bg-raised">
          Export EDL
        </a>
      </div>
      {blocked && <p className="text-sm text-rec-ink">{blocked}</p>}
    </div>
  );
}
