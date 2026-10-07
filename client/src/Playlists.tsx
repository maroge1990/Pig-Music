import { Cover } from "./Cover";
import { MusicLink } from "./MusicLink";
import { shuffled } from "./shuffle";
import { apiFetch as fetch } from "./api";
import { useEffect, useState } from "react";

import { ArrowLeft, Check, Play, Shuffle } from "lucide-react";

import type { Track } from "./types";

import { SongActions } from "./SongActions";
import { usePlayer } from "./Player";

type Entry = Track & { entry_id: string; saved_track: Track | null };

type Playlist = {
  id: string;
  name: string;
  track_count: number;
  available_count: number;
  entries?: Entry[];
  plex?: {
    status?: string;
    available_count?: number;
    pending_count?: number;
    repeated_count?: number;
  };
};

export function Playlists({
  notify,
  favourites = false,
  initialId,
}: {
  initialId?: string;
  favourites?: boolean;
  review: (id: string) => void;
  notify: (text: string) => void;
}) {
  const [items, setItems] = useState<Playlist[]>([]);

  const [detail, setDetail] = useState<Playlist | null>(null);

  const player = usePlayer();

  useEffect(() => {
    let active = true;
    const update = () => {
      if (document.hidden) return Promise.resolve();
      return fetch("/api/playlists")
        .then((r) => r.json())
        .then((v) => {
          if (active)
            setItems(
              v.filter(
                (p: { favourites?: boolean }) => !!p.favourites === favourites,
              ),
            );
        })
        .catch(() => {});
    };
    void update();
    const timer = setInterval(update, 30000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [favourites]);

  useEffect(() => {
    if (!detail) return;
    let active = true;
    const timer = setInterval(() => {
      if (document.hidden) return;
      fetch("/api/playlists/" + detail.id)
        .then((r) => r.json())
        .then((v) => {
          if (active) setDetail(v);
        })
        .catch(() => {});
    }, 15000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [detail?.id]);

  useEffect(() => {
    setDetail(null);
    setItems([]);
  }, [favourites]);
  useEffect(() => {
    if (favourites && items.some((p) => p.id === "pig-favourites"))
      void open("pig-favourites");
  }, [items.some((p) => p.id === "pig-favourites"), favourites]);
  useEffect(() => {
    if (initialId) void open(initialId);
    else if (!favourites) setDetail(null);
  }, [initialId]);
  async function open(id: string) {
    try {
      const r = await fetch("/api/playlists/" + id);
      if (!r.ok) throw new Error("Playlist unavailable.");
      setDetail(await r.json());
    } catch (e) {
      notify((e as Error).message);
    }
  }

  if (!detail)
    return (
      <>
        <div className="section-title">
          <h2>{favourites ? "Favourites" : "Playlists"}</h2>
        </div>
        <div className="album-grid">
          {items.map((p) => (
            <button
              className="album-card"
              key={p.id}
              onClick={() => {
                location.hash = "/library/playlist/" + p.id;
              }}
            >
              <strong>{p.name}</strong>
              <div className="card-caption">
                {p.available_count} of {p.track_count} songs available
              </div>
            </button>
          ))}
        </div>
      </>
    );

  const entries = detail.entries || [];

  const playable = entries
    .filter((e) => e.saved_track)
    .map((e) => e.saved_track!);

  return (
    <>
      <button
        className="back-link"
        onClick={() => {
          setDetail(null);
          location.hash = "/library";
        }}
      >
        <ArrowLeft size={16} />
        Playlists
      </button>
      <div className="section-title">
        <h1>{detail.name}</h1>
      </div>
      <p>
        {detail.available_count} of {detail.track_count} songs available
      </p>
      <div className="release-actions">
        <button
          className="primary-button"
          disabled={!playable.length}
          onClick={() => player.playSaved(playable[0], playable, 0)}
        >
          <Play size={16} />
          Play
        </button>
        <button
          className="secondary-button"
          disabled={!playable.length}
          onClick={() => {
            const queue = shuffled(playable);
            player.playSaved(queue[0], queue, 0);
          }}
        >
          <Shuffle size={16} /> Shuffle
        </button>
      </div>
      <div className="track-list">
        {entries.map((e, index) => (
          <div className="track-row playlist-track-row" key={e.entry_id}>
            <button
              className="track-position track-play"
              aria-label={`Play ${e.title}`}
              disabled={!e.saved_track}
              onClick={() => {
                if (e.saved_track)
                  player.playSaved(
                    e.saved_track,
                    playable,
                    entries.slice(0, index).filter((t) => t.saved_track).length,
                  );
              }}
            >
              {e.saved_track ? <Play size={15} /> : index + 1}
            </button>
            <Cover
              title={e.album}
              src={e.saved_track?.cover_url || e.cover_url}
            />
            <div className="track-name">
              <strong>{e.title}</strong>
              <span>
                <MusicLink artist={e.artist} /> ·{" "}
                <MusicLink artist={e.artist} album={e.album} />
              </span>
            </div>
            <SongActions
              hidePlaylist
              song={{ playlist_id: detail.id, position: index }}
              title={e.title}
            />
            {e.saved_track ? (
              <Check size={17} className="saved-icon" />
            ) : (
              <span className="track-quality">
                {e.status === "review" ? "Check version" : "Missing"}
              </span>
            )}
          </div>
        ))}
      </div>
      {detail.plex?.status && (
        <p className="section-description">
          Plexamp: {detail.plex.available_count || 0} songs available
          {detail.plex.pending_count
            ? ` · ${detail.plex.pending_count} awaiting files or indexing`
            : ""}
          {detail.plex.repeated_count
            ? ` · repeated songs appear once in Plexamp`
            : ""}
        </p>
      )}
    </>
  );
}
