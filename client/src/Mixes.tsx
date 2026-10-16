import { useEffect, useRef, useState } from "react";
import { Play, X } from "lucide-react";
import { api } from "./api";
import { usePlayer } from "./Player";
import { SongRow } from "./SongRow";
import { fromTrack, type Song } from "./songs";
import type { Track } from "./types";
import "./mixes.css";

type Mix = {
  id: string;
  kind: string;
  title: string;
  day: string;
  reason: string;
  tracks: Track[];
};
type MixFeed = { mixes: Mix[]; preparing: boolean };

/** Cover family: interlocking blend, artist orbit, genre waves, chart bars, rewind. */
export function MixArtwork({ kind }: { kind: string }) {
  const palette = ["daily", "artist", "genre", "popular", "back"].includes(kind)
    ? kind
    : "daily";
  const background = `var(--mix-${palette}-background)`;
  const ink = `var(--mix-${palette}-foreground)`;
  return (
    <svg className="mix-artwork" viewBox="0 0 200 200" aria-hidden="true">
      <rect width="200" height="200" fill={background} />
      <g fill="none" stroke={ink} strokeWidth="12">
        {kind === "daily" && (
          <>
            <circle cx="77" cy="90" r="43" />
            <circle cx="123" cy="116" r="43" />
          </>
        )}
        {kind === "artist" && (
          <>
            <circle cx="100" cy="100" r="57" />
            <ellipse
              cx="100"
              cy="100"
              rx="83"
              ry="26"
              transform="rotate(-35 100 100)"
            />
            <circle cx="100" cy="100" r="13" fill={ink} />
          </>
        )}
        {kind === "genre" &&
          [0, 1, 2, 3].map((i) => (
            <path
              key={i}
              d={`M-10 ${65 + i * 26} Q40 ${5 + i * 26} 100 ${65 + i * 26} T210 ${65 + i * 26}`}
            />
          ))}
        {kind === "popular" &&
          [0, 1, 2, 3].map((i) => (
            <rect
              key={i}
              x={35 + i * 36}
              y={122 - i * 24}
              width="20"
              height={45 + i * 24}
              fill={ink}
              stroke="none"
            />
          ))}
        {kind === "back" && (
          <path
            d="M95 57 L42 100 L95 143 Z M156 57 L103 100 L156 143 Z"
            fill={ink}
            stroke="none"
          />
        )}
      </g>
      <path d="M18 182 H182" stroke={ink} strokeWidth="2" opacity=".5" />
      <circle cx="181" cy="19" r="5" fill={ink} />
    </svg>
  );
}

function songs(mix: Mix): Song[] {
  return mix.tracks.map((t) => ({
    ...fromTrack({ ...t, id: t.library_track_id || t.id }),
    cache_id: t.id,
  }));
}

export function Mixes() {
  const [feed, setFeed] = useState<MixFeed | null>(null);
  const [selected, setSelected] = useState<Mix | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const load = () => {
      if (document.hidden) {
        timer = setTimeout(load, 30000);
        return;
      }
      void api<MixFeed>("/v1/home/mixes", { signal: controller.signal })
        .then((value) => {
          if (!controller.signal.aborted) {
            setFeed(value);
            setError("");
            timer = setTimeout(load, value.preparing ? 30000 : 300000);
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted) {
            setError(e.message);
            timer = setTimeout(load, 60000);
          }
        });
    };
    load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [revision]);
  return (
    <section className="home-section" aria-label="Your mixes">
      <h2>Your mixes</h2>
      <p>Familiar favourites. Something new. Made for today.</p>
      {feed?.mixes.length ? (
        <div className="mix-row">
          {feed.mixes.map((mix) => (
            <button
              className="album-card mix-card"
              key={mix.id}
              onClick={() => setSelected(mix)}
            >
              <MixArtwork kind={mix.kind} />
              <strong>{mix.title}</strong>
              <span>
                {[...new Set(mix.tracks.map((t) => t.artist))]
                  .slice(0, 3)
                  .join(" · ")}
              </span>
              <small>
                {mix.tracks.length} {mix.tracks.length === 1 ? "song" : "songs"}{" "}
                · Ready to play
              </small>
            </button>
          ))}
        </div>
      ) : (
        <p role="status">
          {error ||
            (feed
              ? feed.preparing
                ? "Preparing your mixes. They'll appear once their audio is ready."
                : "Your mixes appear as your library grows. Discoveries are prepared ahead of playback."
              : "Preparing your mixes…")}
        </p>
      )}
      {feed?.preparing && !!feed.mixes.length && (
        <small role="status">
          Preparing more mixes. These are ready to play.
        </small>
      )}
      {selected && (
        <MixDetails
          key={selected.id}
          mix={selected}
          onClose={() => setSelected(null)}
          onChange={() => setRevision((value) => value + 1)}
          onHide={() => {
            setFeed(
              (value) =>
                value && {
                  ...value,
                  mixes: value.mixes.filter((mix) => mix.id !== selected.id),
                },
            );
            setSelected(null);
          }}
        />
      )}
    </section>
  );
}

function MixDetails({
  mix,
  onClose,
  onChange,
  onHide,
}: {
  mix: Mix;
  onClose: () => void;
  onChange: () => void;
  onHide: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const player = usePlayer();
  const [queue, setQueue] = useState(() => songs(mix));
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  async function hide(song: Song) {
    try {
      await api("/v1/mixes/hide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ track_id: song.cache_id }),
      });
      setQueue((current) => current.filter((t) => t.key !== song.key));
      setNotice("Hidden from future mixes.");
      onChange();
    } catch (e) {
      setNotice((e as Error).message);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="mix-dialog"
      onClose={onClose}
      aria-labelledby="mix-title"
    >
      <button
        className="mix-close"
        aria-label="Close mix"
        onClick={() => dialog.current?.close()}
      >
        <X size={20} />
      </button>
      <div className="mix-heading">
        <MixArtwork kind={mix.kind} />
        <div>
          <small>{mix.day}</small>
          <h2 id="mix-title">{mix.title}</h2>
          <p>{mix.reason}</p>
        </div>
      </div>
      <div className="mix-actions">
        <button
          className="primary"
          disabled={!queue.length}
          onClick={() => {
            player.play(queue);
            dialog.current?.close();
          }}
        >
          <Play size={16} /> Play mix
        </button>
        <button
          disabled={saving}
          onClick={() => {
            setSaving(true);
            void api("/v1/mixes/" + mix.id + "/save", { method: "POST" })
              .then(() => {
                setNotice(
                  "Playlist saved. Add songs to your library to keep their audio after this mix leaves rotation.",
                );
                window.dispatchEvent(new Event("music-library-changed"));
              })
              .catch((e) => setNotice(e.message))
              .finally(() => setSaving(false));
          }}
        >
          Save this edition
        </button>
      </div>
      <details className="mix-options">
        <summary>Mix options</summary>
        <p>Hide this edition until the next daily rotation.</p>
        <button
          disabled={saving}
          onClick={() => {
            setSaving(true);
            void api("/v1/mixes/" + mix.id + "/hide", { method: "POST" })
              .then(onHide)
              .catch((e) => setNotice(e.message))
              .finally(() => setSaving(false));
          }}
        >
          Hide this edition
        </button>
      </details>
      {notice && <p role="status">{notice}</p>}
      <div className="song-list">
        {queue.map((song, index) => (
          <SongRow
            key={song.key}
            song={song}
            queue={queue}
            index={index}
            menu={
              <button role="menuitem" onClick={() => void hide(song)}>
                Hide from mixes
              </button>
            }
          />
        ))}
      </div>
    </dialog>
  );
}
