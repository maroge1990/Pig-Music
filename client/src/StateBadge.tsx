import type { ReactNode } from "react";
import { CircleAlert, CircleCheck, Clock, LoaderCircle } from "lucide-react";

export type BadgeState =
  | "library"
  | "requested"
  | "active"
  | "failed"
  | "neutral";

const defaults: Record<BadgeState, { label: string; icon: ReactNode }> = {
  library: { label: "In your library", icon: <CircleCheck size={14} /> },
  requested: { label: "Requested", icon: <Clock size={14} /> },
  active: {
    label: "Downloading",
    icon: <LoaderCircle size={14} className="spin" />,
  },
  failed: { label: "Failed", icon: <CircleAlert size={14} /> },
  neutral: { label: "", icon: null },
};

/** The one place a song's or download's state is shown: icon plus words. */
export function StateBadge({
  state,
  label,
  iconOnly = false,
}: {
  state: BadgeState;
  label?: string;
  iconOnly?: boolean;
}) {
  const text = label ?? defaults[state].label;
  const icon = defaults[state].icon;
  if (iconOnly)
    return (
      <span
        className="state-badge icon-only"
        data-state={state}
        role="img"
        aria-label={text}
        title={text}
      >
        {icon}
      </span>
    );
  return (
    <span className="state-badge" data-state={state}>
      {icon}
      {text}
    </span>
  );
}
