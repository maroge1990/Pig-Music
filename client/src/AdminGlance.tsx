import { useEffect, useState } from "react";
import { api } from "./api";
import type { Queue } from "./QueueView";
import type { Library } from "./types";

const ACTIVE = [
  "waiting_for_sources",
  "searching",
  "downloading",
  "validating",
  "importing",
];

/** The few numbers an administrator acts on, each linking to its section. */
export function AdminGlance({
  queue,
  library,
}: {
  queue: Queue | null;
  library: Library | null;
}) {
  const [people, setPeople] = useState<number | null>(null);
  const [unassigned, setUnassigned] = useState<number | string | null>(null);
  useEffect(() => {
    void api<{ people: { disabled?: boolean }[] }>("/v1/people")
      .then((d) => setPeople(d.people.filter((p) => !p.disabled).length))
      .catch(() => setPeople(null));
    void api<{ albums: unknown[]; next_offset: number | null }>(
      "/v1/admin/unassigned?offset=0",
    )
      .then((d) =>
        setUnassigned(
          d.next_offset === null ? d.albums.length : `${d.albums.length}+`,
        ),
      )
      .catch(() => setUnassigned(null));
  }, []);
  const items = queue?.items || [];
  const tiles = [
    {
      label: "Queued or downloading",
      value: items.filter((i) => ACTIVE.includes(i.status)).length,
      note: queue && !queue.downloads_enabled ? "Downloads are paused" : "",
      href: "#/admin/downloads",
    },
    {
      label: "Failed requests",
      value: items.filter((i) => i.status === "failed").length,
      href: "#/admin/downloads",
      warn: true,
    },
    {
      label: "Albums awaiting an owner",
      value: unassigned,
      href: "#/admin/library",
      warn: true,
    },
    {
      label: "Files needing attention",
      value: library ? library.snapshot.read_failures?.length || 0 : null,
      href: "#/admin/library",
      warn: true,
    },
    { label: "People", value: people, href: "#/admin/people" },
  ];
  return (
    <ul className="admin-glance" aria-label="At a glance">
      {tiles.map((tile) => (
        <li key={tile.label}>
          <a
            href={tile.href}
            className={tile.warn && tile.value ? "needs-attention" : ""}
          >
            <strong>{tile.value ?? "–"}</strong>
            <span>{tile.label}</span>
            {tile.note && <small>{tile.note}</small>}
          </a>
        </li>
      ))}
    </ul>
  );
}
