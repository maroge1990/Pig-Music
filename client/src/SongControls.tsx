import { ArrowDown, Check, Clock, LoaderCircle, Play } from "lucide-react";

export type SongState = {
  title: string;
  status?: string;
  download_status?: string;
  received_bytes?: number;
  total_bytes?: number;
};

export function isPending(song?: SongState) {
  return [
    "waiting_for_sources",
    "searching",
    "downloading",
    "validating",
    "importing",
  ].includes(song?.download_status || "");
}

/** Shared catalogue/popularity actions: one order, state vocabulary and hit area. */
export function SongControls({
  song,
  busy = false,
  selected = false,
  play,
  download,
}: {
  song: SongState;
  busy?: boolean;
  selected?: boolean;
  play: () => void;
  download: () => void;
}) {
  const saved = song.status === "downloaded";
  const active = isPending(song);
  const waiting = song.download_status === "waiting_for_sources";
  const percent = song.total_bytes
    ? Math.round(((song.received_bytes || 0) * 100) / song.total_bytes)
    : 0;
  const label = saved
    ? "Downloaded"
    : selected
      ? "Selected"
      : waiting
        ? "Queued"
        : active
          ? `Downloading ${percent}%`
          : song.download_status === "failed"
            ? "Retry download"
            : "Download";
  return (
    <>
      <button
        className="round-action"
        aria-label={`Play ${song.title}${saved ? "" : " remotely"}`}
        title={saved ? "Play saved song" : "Play remotely · experimental"}
        disabled={busy}
        onClick={play}
      >
        <Play size={15} />
      </button>
      <button
        className={`round-action download-circle ${saved ? "complete" : active ? "queued" : ""}`}
        aria-label={`${label} ${song.title}`}
        title={label}
        disabled={saved || active || busy}
        onClick={download}
      >
        {saved ? (
          <Check size={17} />
        ) : selected || busy || (active && !waiting) ? (
          <LoaderCircle className="spin" size={17} />
        ) : waiting ? (
          <Clock size={17} />
        ) : (
          <ArrowDown size={17} />
        )}
      </button>
    </>
  );
}
