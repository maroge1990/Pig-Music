import { apiFetch } from "./api";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  ChevronDown,
  Play,
  Pause,
  SkipBack,
  SkipForward,
  Square,
  Volume2,
  VolumeX,
  LoaderCircle,
} from "lucide-react";
import type { Track } from "./types";
import { PersonalSongActions } from "./PersonalSongActions";
import { useFixedHeight } from "./useFixedHeight";
import { Cover } from "./Cover";
import {
  fromTrack,
  goToAlbum,
  goToArtist,
  requestSong,
  type Song,
} from "./songs";

type Playing = Song & {
  url?: string;
  source?: string;
  note?: string;
  /** Library track behind the audio, for play history. */
  saved_id?: string;
};
type Controls = {
  /** Play `queue[index]`, then carry on through the queue. */
  play: (queue: Song[], index?: number) => void;
  playNext: (song: Song) => void;
  addToQueue: (song: Song) => void;
  playSaved: (track: Track, queue?: Track[], position?: number) => void;
  current: string | null;
};
const Context = createContext<Controls>({
  play: () => {},
  playNext: () => {},
  addToQueue: () => {},
  playSaved: () => {},
  current: null,
});
export const usePlayer = () => useContext(Context);
const time = (n: number) =>
  `${Math.floor((n || 0) / 60)}:${String(Math.floor((n || 0) % 60)).padStart(2, "0")}`;

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement>(null);
  const serial = useRef(0);
  const queue = useRef<Song[]>([]);
  const cursor = useRef(-1);
  const playEvent = useRef<{
    event_id: string;
    track_id: string;
    played_at: number;
    seconds: number;
    last: number;
  } | null>(null);
  function reportPlay() {
    const event = playEvent.current;
    playEvent.current = null;
    if (event && event.seconds >= 1) {
      const { last: _last, ...body } = event;
      void apiFetch("/api/v1/play-events", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          events: [{ ...body, seconds: Math.floor(body.seconds) }],
        }),
      }).catch(() => {});
    }
  }
  const [song, setSong] = useState<Playing | null>(null);
  const [expanded, setExpanded] = useState(false);
  const bar = useFixedHeight("--player-height", !!song);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [muted, setMuted] = useState(false);
  const [, setQueueVersion] = useState(0);

  useEffect(() => {
    const stop = () => {
      playEvent.current = null;
      ++serial.current;
      audio.current?.pause();
      audio.current?.removeAttribute("src");
      queue.current = [];
      cursor.current = -1;
      setSong(null);
      setExpanded(false);
      setBusy(false);
      if ("mediaSession" in navigator) navigator.mediaSession.metadata = null;
    };
    window.addEventListener("music-auth-required", stop);
    window.addEventListener("music-signed-out", stop);
    return () => {
      window.removeEventListener("music-auth-required", stop);
      window.removeEventListener("music-signed-out", stop);
    };
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("now-playing-open", expanded);
    if (!expanded) return;
    const close = (e: KeyboardEvent) =>
      e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [expanded]);
  const collapse = () => setExpanded(false);

  /** Resolve the audio for one song: your file, or a stream when unsaved. */
  async function resolve(s: Song) {
    if (s.state === "server" && s.server) {
      // On the server already: adding to your library is instant.
      await requestSong(s);
      return resolveSaved(s.server.id);
    }
    if (s.saved) return resolveSaved(s.saved.id);
    if (s.release_id && (s.track_id || s.recording_id)) {
      const response = await apiFetch("/api/playback/catalogue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          release_id: s.release_id,
          track_id: s.track_id,
          recording_id: s.track_id ? undefined : s.recording_id,
        }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "This song can't be streamed right now.",
        );
      return {
        url: body.url as string,
        source: body.source as string,
        note: body.note as string | undefined,
        saved_id:
          body.source === "Saved library" ? (body.id as string) : undefined,
      };
    }
    throw new Error("This song can't be streamed. Download it to listen.");
  }
  async function resolveSaved(id: string) {
    const response = await apiFetch(
      "/api/v1/playback/" + encodeURIComponent(id) + "/url",
      { method: "POST" },
    );
    const body = await response.json();
    if (!response.ok)
      throw new Error(
        typeof body.detail === "string" ? body.detail : "Playback unavailable.",
      );
    return { url: body.url as string, source: "Saved library", saved_id: id };
  }

  async function load(s: Song) {
    reportPlay();
    const request = ++serial.current;
    audio.current?.pause();
    setSong({ ...s });
    setBusy(true);
    setError("");
    setPosition(0);
    setDuration(s.duration || 0);
    try {
      const found = await resolve(s);
      if (request !== serial.current) return;
      playEvent.current = found.saved_id
        ? {
            event_id: crypto.randomUUID(),
            track_id: found.saved_id,
            played_at: Math.floor(Date.now() / 1000),
            seconds: 0,
            last: 0,
          }
        : null;
      setSong({ ...s, ...found });
    } catch (e) {
      if (request === serial.current) setError((e as Error).message);
    } finally {
      if (request === serial.current) setBusy(false);
    }
  }
  function play(songs: Song[], index = 0) {
    if (!songs[index]) return;
    queue.current = songs;
    cursor.current = index;
    setQueueVersion((v) => v + 1);
    void load(songs[index]);
  }
  function playSaved(
    track: Track,
    tracks: Track[] = [track],
    position?: number,
  ) {
    const index = position ?? tracks.findIndex((t) => t.id === track.id);
    play(
      tracks.map((t) => fromTrack(t)),
      Math.max(0, index),
    );
  }
  function playNext(s: Song) {
    if (!song) return play([s]);
    queue.current.splice(cursor.current + 1, 0, s);
    setQueueVersion((v) => v + 1);
  }
  function addToQueue(s: Song) {
    if (!song) return play([s]);
    queue.current.push(s);
    setQueueVersion((v) => v + 1);
  }
  function step(delta: number) {
    const index = cursor.current + delta;
    const next = queue.current[index];
    if (!next) return;
    cursor.current = index;
    setQueueVersion((v) => v + 1);
    void load(next);
  }
  const index = cursor.current;
  const hasNext = index >= 0 && index < queue.current.length - 1;
  useEffect(() => {
    if (!song?.url) return;
    void audio.current
      ?.play()
      .catch(() => setError("Tap Play to start audio on this device."));
    if ("mediaSession" in navigator) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: song.title,
        artist: song.artist,
        album: song.album,
        artwork: song.cover
          ? [{ src: new URL(song.cover, location.href).href }]
          : [],
      });
      const handlers: { [key: string]: MediaSessionActionHandler } = {
        play: () => {
          void audio.current?.play();
        },
        pause: () => audio.current?.pause(),
        previoustrack: () => step(-1),
        nexttrack: () => step(1),
        seekto: (details) => {
          if (audio.current && details.seekTime !== undefined)
            audio.current.currentTime = details.seekTime;
        },
      };
      for (const [action, handler] of Object.entries(handlers))
        try {
          navigator.mediaSession.setActionHandler(
            action as MediaSessionAction,
            handler,
          );
        } catch {
          /* device does not support this action */
        }
    }
    return () => {
      if ("mediaSession" in navigator)
        for (const action of [
          "play",
          "pause",
          "previoustrack",
          "nexttrack",
          "seekto",
        ])
          try {
            navigator.mediaSession.setActionHandler(
              action as MediaSessionAction,
              null,
            );
          } catch {
            /* unsupported */
          }
    };
  }, [song?.url]);
  function close() {
    reportPlay();
    serial.current++;
    audio.current?.pause();
    setSong(null);
    setExpanded(false);
    setError("");
    setBusy(false);
    queue.current = [];
    cursor.current = -1;
    if ("mediaSession" in navigator) navigator.mediaSession.metadata = null;
  }
  function toggle() {
    if (!audio.current) return;
    if (playing) audio.current.pause();
    else
      void audio.current
        .play()
        .then(() => setError(""))
        .catch(() =>
          setError(
            "Audio could not start. Try another browser or download this song.",
          ),
        );
  }
  const playButton = (size: number) => (
    <button
      className="np-play"
      aria-label={playing ? "Pause" : "Play"}
      disabled={busy || !song?.url}
      onClick={toggle}
    >
      {busy ? (
        <LoaderCircle size={size} className="spin" />
      ) : playing ? (
        <Pause size={size} fill="currentColor" />
      ) : (
        <Play size={size} fill="currentColor" />
      )}
    </button>
  );
  const progress = duration ? Math.min(1, position / duration) : 0;
  return (
    <Context.Provider
      value={{
        play,
        playNext,
        addToQueue,
        playSaved,
        current: song?.key || null,
      }}
    >
      <div className={song ? "media-shell has-player" : "media-shell"}>
        {children}
        <audio
          ref={audio}
          src={song?.url}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={() => {
            const current = audio.current?.currentTime || 0;
            const event = playEvent.current;
            if (event) {
              const elapsed = current - event.last;
              if (playing && elapsed > 0 && elapsed < 3)
                event.seconds += elapsed;
              event.last = current;
            }
            setPosition(current);
          }}
          onDurationChange={() => {
            const n = audio.current?.duration;
            if (n && Number.isFinite(n)) setDuration(n);
          }}
          onEnded={() => {
            reportPlay();
            setPlaying(false);
            step(1);
          }}
          onError={() => {
            if (song?.url)
              setError(
                "This audio stream could not be played. The provider or format may be unavailable.",
              );
          }}
        />
        {song && (
          <section ref={bar} className="mini-player" aria-label="Now playing">
            <button
              className="mini-open"
              aria-label={`Open now playing: ${song.title}`}
              onClick={() => setExpanded(true)}
            >
              <Cover title={song.title} src={song.cover} sizes="48px" />
              <span>
                <strong>{song.title}</strong>
                <small>
                  {busy
                    ? "Finding audio…"
                    : error
                      ? error
                      : song.source && song.source !== "Saved library"
                        ? `${song.artist} · Streaming`
                        : song.artist}
                </small>
              </span>
            </button>
            {playButton(22)}
            <button
              className="mini-next"
              aria-label="Next song"
              disabled={!hasNext || busy}
              onClick={() => step(1)}
            >
              <SkipForward size={22} fill="currentColor" />
            </button>
            <span
              className="mini-progress"
              aria-hidden="true"
              style={{ transform: `scaleX(${progress})` }}
            />
          </section>
        )}
        {song && expanded && (
          <section
            className="now-playing"
            role="dialog"
            aria-modal="true"
            aria-label="Now playing"
          >
            <div className="now-playing-backdrop" aria-hidden="true">
              {song.cover && (
                <Cover title={song.title} src={song.cover} sizes="128px" />
              )}
            </div>
            <button
              className="np-collapse"
              aria-label="Close now playing"
              autoFocus
              onClick={collapse}
            >
              <ChevronDown size={28} />
            </button>
            <Cover
              className="np-cover"
              title={song.title}
              src={song.cover}
              sizes="(max-width: 600px) 90vw, 420px"
            />
            <div className="np-meta">
              <h2>{song.title}</h2>
              <p>
                <button
                  className="music-text-link"
                  onClick={() => {
                    collapse();
                    void goToArtist(song.artist, song.artist_id).catch(
                      () => {},
                    );
                  }}
                >
                  {song.artist}
                </button>
                {song.album && (
                  <>
                    {" · "}
                    <button
                      className="music-text-link"
                      onClick={() => {
                        collapse();
                        void goToAlbum(
                          song.album!,
                          song.album_artist || song.artist,
                          song.release_id,
                          song.artist_id,
                        ).catch(() => {});
                      }}
                    >
                      {song.album}
                    </button>
                  </>
                )}
              </p>
              {song.note && <small>{song.note}</small>}
            </div>
            <div className="np-seek">
              <input
                aria-label="Playback position"
                type="range"
                min="0"
                max={duration || 1}
                step="0.1"
                value={Math.min(position, duration || 1)}
                disabled={!song.url}
                onChange={(e) => {
                  if (audio.current)
                    audio.current.currentTime = Number(e.target.value);
                }}
              />
              <span>{time(position)}</span>
              <span>-{time(Math.max(0, duration - position))}</span>
            </div>
            <div className="np-transport">
              <button
                aria-label="Previous song"
                disabled={index <= 0 || busy}
                onClick={() =>
                  position > 3 && audio.current
                    ? (audio.current.currentTime = 0)
                    : step(-1)
                }
              >
                <SkipBack size={30} fill="currentColor" />
              </button>
              {playButton(34)}
              <button
                aria-label="Next song"
                disabled={!hasNext || busy}
                onClick={() => step(1)}
              >
                <SkipForward size={30} fill="currentColor" />
              </button>
            </div>
            <div className="np-actions">
              <PersonalSongActions
                track={{
                  id: song.saved_id || song.key,
                  title: song.title,
                  artist: song.artist,
                  album: song.album || "",
                  album_artist: song.album_artist || song.artist,
                  duration: song.duration || 0,
                  disc_number: 1,
                  track_number: 0,
                }}
              />
              <button
                aria-label={muted ? "Unmute" : "Mute"}
                onClick={() => {
                  setMuted(!muted);
                  if (audio.current) audio.current.muted = !muted;
                }}
              >
                {muted ? <VolumeX size={20} /> : <Volume2 size={20} />}
              </button>
              <button aria-label="Stop and close player" onClick={close}>
                <Square size={18} />
              </button>
            </div>
            {error && (
              <p className="np-error" role="alert">
                {error}
              </p>
            )}
            {queue.current.length > index + 1 && (
              <section className="np-queue" aria-label="Up next">
                <h3>Up next</h3>
                <ol>
                  {queue.current.slice(index + 1, index + 6).map((s, i) => (
                    <li key={s.key + i}>
                      <button onClick={() => step(i + 1)}>
                        <strong>{s.title}</strong>
                        <small>{s.artist}</small>
                      </button>
                    </li>
                  ))}
                </ol>
              </section>
            )}
          </section>
        )}
      </div>
    </Context.Provider>
  );
}
