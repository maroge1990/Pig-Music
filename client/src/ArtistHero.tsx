import { api } from "./api";
import { useEffect, useRef, useState } from "react";
import { CircleCheck } from "lucide-react";
import { Cover } from "./Cover";
import type { Artist } from "./types";
export function ArtistHero({
  artist,
  discovered = false,
}: {
  artist: Artist;
  discovered?: boolean;
}) {
  const [revision, setRevision] = useState(0);
  const background = `/api/${discovered ? "catalogue/" : ""}artists/${artist.id}/background?r=${revision}`;
  const scene = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState(false);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    setLoaded(false);
    void api<{ media?: { fanart_configured: boolean; portraits: boolean } }>(
      "/library",
      { signal: controller.signal },
    )
      .then((s) => {
        if (!controller.signal.aborted)
          setEnabled(Boolean(s.media?.fanart_configured && s.media?.portraits));
      })
      .catch(() => {});
    return () => controller.abort();
  }, [artist.id]);
  useEffect(() => {
    const changed = () => setRevision((r) => r + 1);
    window.addEventListener("music-artwork-changed", changed);
    window.addEventListener("music-artwork-retry", changed);
    return () => {
      window.removeEventListener("music-artwork-changed", changed);
      window.removeEventListener("music-artwork-retry", changed);
    };
  }, []);
  useEffect(() => {
    const node = scene.current;
    if (!node || !loaded) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    const phone = window.matchMedia("(max-width: 600px)");
    let frame = 0;
    let start = 0;
    let height = 1;
    const measure = () => {
      start = node.getBoundingClientRect().top + window.scrollY;
      height = node.offsetHeight;
    };
    measure();
    const update = () => {
      frame = 0;
      const progress = Math.min(
        1,
        Math.max(0, (window.scrollY - start) / Math.max(1, height * 0.8)),
      );
      node.style.setProperty("--artist-opacity", String(1 - progress));
      node.style.setProperty("--artist-progress", String(progress));
      node.style.setProperty(
        "--artist-blur",
        `${reduced.matches || phone.matches ? 0 : progress * 18}px`,
      );
      node.style.setProperty(
        "--artist-shift",
        `${reduced.matches || phone.matches ? 0 : progress * height * 0.55}px`,
      );
    };
    const scroll = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    const resize = () => {
      measure();
      scroll();
    };
    update();
    window.addEventListener("scroll", scroll, { passive: true });
    window.addEventListener("resize", resize);
    reduced.addEventListener("change", scroll);
    return () => {
      window.removeEventListener("scroll", scroll);
      window.removeEventListener("resize", resize);
      reduced.removeEventListener("change", scroll);
      cancelAnimationFrame(frame);
    };
  }, [loaded, artist.id]);
  return (
    <div
      ref={scene}
      className={`artist-scene ${loaded ? "has-background" : ""}`}
    >
      {enabled && (
        <div className="artist-backdrop" aria-hidden="true">
          <img
            className="artist-photo artist-photo-sharp"
            alt=""
            src={`${background}&w=1024`}
            srcSet={`${background}&w=512 512w, ${background}&w=1024 1024w`}
            sizes="100vw"
            onLoad={() => setLoaded(true)}
            onError={() => setLoaded(false)}
          />
          <img
            className="artist-photo artist-photo-soft"
            alt=""
            src={`${background}&w=128&soft=true`}
          />
        </div>
      )}
      <div className="detail-hero artist-hero">
        <Cover artist title={artist.name} src={artist.cover_url} />
        <div className="artist-identity">
          <h1>{artist.name}</h1>
          {!discovered && (
            <p>
              {artist.album_count}{" "}
              {artist.album_count === 1 ? "release" : "releases"} <span>·</span>{" "}
              {artist.track_count} saved tracks
            </p>
          )}
          {!discovered && (
            <span className="status-pill">
              <CircleCheck size={14} />
              In your library
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
