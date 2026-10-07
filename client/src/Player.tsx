import { apiFetch as fetch } from "./api";
import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  X,
  Volume2,
  VolumeX,
  LoaderCircle,
} from "lucide-react";
import type { Track } from "./types";
import { PersonalSongActions } from "./PersonalSongActions";
import { MusicLink } from "./MusicLink";
import { useFixedHeight } from "./useFixedHeight";
import { Cover } from "./Cover";

type Playing = {
  saved_id?: string;
  release_id?: string;
  id: string;
  title: string;
  artist: string;
  album?: string;
  duration: number;
  url?: string;
  source?: string;
  note?: string;
  cover_url?: string | null;
};
type Controls = {
  playSaved: (track: Track, queue?: Track[], position?: number) => void;
  playCatalogue: (
    releaseId: string,
    track: Playing,
    cover?: string | null,
  ) => void;
};
const Context = createContext<Controls>({
  playSaved: () => {},
  playCatalogue: () => {},
});
export const usePlayer = () => useContext(Context);
const time = (n: number) =>
  `${Math.floor((n || 0) / 60)}:${String(Math.floor((n || 0) % 60)).padStart(2, "0")}`;

export function PlayerProvider({ children }: { children: ReactNode }) {
  const audio = useRef<HTMLAudioElement>(null);
  const serial = useRef(0);
  const queue = useRef<Track[]>([]);
  const cursor = useRef(-1);
  const [song, setSong] = useState<Playing | null>(null);
  const playerBar = useFixedHeight("--player-height", !!song);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [playing, setPlaying] = useState(false);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const [muted, setMuted] = useState(false);

  useEffect(() => {
    const stop = () => {
      ++serial.current;
      audio.current?.pause();
      audio.current?.removeAttribute("src");
      queue.current = [];
      cursor.current = -1;
      setSong(null);
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

  async function load(track: Playing, path: string, options?: RequestInit) {
    const request = ++serial.current;
    audio.current?.pause();
    setSong({ ...track, url: undefined });
    setBusy(true);
    setError("");
    setPosition(0);
    setDuration(track.duration);
    try {
      const saved = path.startsWith("saved/");
      const response = await fetch(
        saved
          ? "/api/v1/playback/" + path.slice(6) + "/url"
          : "/api/playback/" + path,
        saved ? { method: "POST" } : options,
      );
      const body = await response.json();
      if (saved) {
        body.id = track.id;
        body.source = "Saved library";
      }
      if (!response.ok)
        throw new Error(
          typeof body.detail === "string"
            ? body.detail
            : "Playback unavailable.",
        );
      if (request === serial.current)
        setSong({
          ...track,
          ...body,
          saved_id: body.source === "Saved library" ? body.id : track.saved_id,
          cover_url: track.cover_url,
        });
    } catch (e) {
      if (request === serial.current) setError((e as Error).message);
    } finally {
      if (request === serial.current) setBusy(false);
    }
  }
  function playSaved(
    track: Track,
    tracks: Track[] = [track],
    position?: number,
  ) {
    queue.current = tracks;
    cursor.current = position ?? tracks.findIndex((t) => t.id === track.id);
    void load(
      { ...track, saved_id: track.id },
      "saved/" + encodeURIComponent(track.id),
    );
  }
  function playCatalogue(
    releaseId: string,
    track: Playing,
    cover?: string | null,
  ) {
    queue.current = [];
    cursor.current = -1;
    void load(
      { ...track, release_id: releaseId, cover_url: cover },
      "catalogue",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ release_id: releaseId, track_id: track.id }),
      },
    );
  }
  function step(delta: number) {
    const index = cursor.current;
    const next = queue.current[index + delta];
    if (next) playSaved(next, queue.current, index + delta);
  }
  const index = cursor.current;
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
        artwork: song.cover_url
          ? [{ src: new URL(song.cover_url, location.href).href }]
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
    serial.current++;
    audio.current?.pause();
    setSong(null);
    setError("");
    setBusy(false);
    queue.current = [];
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
  return (
    <Context.Provider value={{ playSaved, playCatalogue }}>
      <div className={song ? "media-shell has-player" : "media-shell"}>
        {children}
        <audio
          ref={audio}
          src={song?.url}
          preload="metadata"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onTimeUpdate={() => setPosition(audio.current?.currentTime || 0)}
          onDurationChange={() => {
            const n = audio.current?.duration;
            if (n && Number.isFinite(n)) setDuration(n);
          }}
          onEnded={() => {
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
          <section
            ref={playerBar}
            className="music-player"
            aria-label="Music player"
          >
            <div className="player-song">
              <Cover
                title={song.title}
                src={song.cover_url}
                sizes="(max-width: 600px) 40px, 54px"
              />
              <div>
                <strong>{song.title}</strong>
                <span>
                  <MusicLink artist={song.artist} />
                  {song.album && (
                    <>
                      {" "}
                      ·{" "}
                      <MusicLink
                        album={song.album}
                        artist={song.artist}
                        releaseId={song.release_id}
                      />
                    </>
                  )}
                </span>
                {busy && <small>Finding audio…</small>}
              </div>
            </div>
            <div className="player-controls">
              <div className="player-buttons">
                <button
                  className="icon-button"
                  aria-label="Previous song"
                  disabled={index <= 0 || busy}
                  onClick={() => step(-1)}
                >
                  <SkipBack size={18} />
                </button>
                <button
                  className="player-play"
                  aria-label={playing ? "Pause" : "Play"}
                  disabled={busy || !song.url}
                  onClick={toggle}
                >
                  {busy ? (
                    <LoaderCircle size={20} className="spin" />
                  ) : playing ? (
                    <Pause size={20} />
                  ) : (
                    <Play size={20} />
                  )}
                </button>
                <button
                  className="icon-button"
                  aria-label="Next song"
                  disabled={
                    index < 0 || index >= queue.current.length - 1 || busy
                  }
                  onClick={() => step(1)}
                >
                  <SkipForward size={18} />
                </button>
              </div>
              <div className="player-seek">
                <span>{time(position)}</span>
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
                <span>{time(duration)}</span>
              </div>
            </div>
            <div className="player-extra">
              <PersonalSongActions
                track={{
                  id: song.saved_id || song.id,
                  title: song.title,
                  artist: song.artist,
                  album: song.album || "",
                  album_artist: song.artist,
                  duration: song.duration,
                  disc_number: 1,
                  track_number: 0,
                }}
              />
              <button
                className="icon-button"
                aria-label={muted ? "Unmute" : "Mute"}
                onClick={() => {
                  setMuted(!muted);
                  if (audio.current) audio.current.muted = !muted;
                }}
              >
                {muted ? <VolumeX size={18} /> : <Volume2 size={18} />}
              </button>
              <button
                className="icon-button"
                aria-label="Close player"
                onClick={close}
              >
                <X size={18} />
              </button>
            </div>
            {error && (
              <p className="player-error" role="alert">
                {error}
              </p>
            )}
          </section>
        )}
      </div>
    </Context.Provider>
  );
}
