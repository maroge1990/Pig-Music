import { cachedLibrary, peekLibrary } from "./api";
import { useEffect, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { StateBadge } from "./StateBadge";
import { Cover } from "./Cover";
import type { Artist, Library } from "./types";
export function ArtistHero({
  artist,
  discovered = false,
  back,
}: {
  artist: Artist;
  discovered?: boolean;
  /** Where the back control returns to; it floats over the photograph. */
  back?: { label: string; go: () => void };
}) {
  const [revision, setRevision] = useState(0);
  const base = `/api/v1/${discovered ? "catalogue/" : ""}artists/${artist.id}`;
  const background = `${base}/background?r=${revision}`;
  const logoSrc = `${base}/logo?r=${revision}`;
  // The address that last loaded; a cached image can load before effects run.
  const [loadedLogo, setLoadedLogo] = useState("");
  const logo = loadedLogo === logoSrc;
  const scene = useRef<HTMLDivElement>(null);
  const [enabled, setEnabled] = useState<boolean | null>(() => {
    const library = peekLibrary<Library>();
    return library
      ? Boolean(library.media?.fanart_configured && library.media?.portraits)
      : null;
  });
  const [failedBackground, setFailedBackground] = useState("");
  // Reserve the final layout while cached artwork is decoded; fallback only on failure.
  const immersive = enabled !== false && failedBackground !== background;
  const [loaded, setLoaded] = useState(false);
  // The photograph runs edge to edge from the top of the screen.
  useEffect(() => {
    if (!immersive) return;
    document.documentElement.classList.add("immersive-hero");
    return () => document.documentElement.classList.remove("immersive-hero");
  }, [immersive]);
  useEffect(() => {
    let active = true;
    setLoaded(false);
    void cachedLibrary<Library>()
      .then((library) => {
        if (active)
          setEnabled(
            Boolean(
              library.media?.fanart_configured && library.media?.portraits,
            ),
          );
      })
      .catch(() => {
        if (active) setEnabled(false);
      });
    return () => {
      active = false;
    };
  }, [artist.id]);
  useEffect(() => {
    const changed = () => setRevision((r) => r + 1);
    // Look again only while the photograph is missing; a new address for a
    // loaded image would download it again and bypass the cache.
    const retry = () => {
      if (!loaded) changed();
    };
    window.addEventListener("music-artwork-changed", changed);
    window.addEventListener("music-artwork-retry", retry);
    return () => {
      window.removeEventListener("music-artwork-changed", changed);
      window.removeEventListener("music-artwork-retry", retry);
    };
  }, [loaded]);
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
      className={`artist-scene ${immersive ? "has-background" : ""}`}
    >
      {back && (
        <button className="hero-back" onClick={back.go}>
          <ChevronLeft size={22} />
          <span>{back.label}</span>
        </button>
      )}
      {enabled && (
        <div className="artist-backdrop" aria-hidden="true">
          <img
            className="artist-photo artist-photo-sharp"
            alt=""
            src={`${background}&w=1024`}
            srcSet={`${background}&w=512 512w, ${background}&w=1024 1024w`}
            sizes="100vw"
            onLoad={() => setLoaded(true)}
            onError={() => {
              setLoaded(false);
              setFailedBackground(background);
            }}
          />
          <img
            className="artist-photo artist-photo-soft"
            alt=""
            src={`${background}&w=128&soft=true`}
          />
        </div>
      )}
      <div className="detail-hero artist-hero">
        <Cover
          artist
          title={artist.name}
          src={artist.cover_url}
          sizes="(max-width: 600px) 160px, (max-width: 800px) 130px, (max-width: 1200px) 170px, 210px"
        />
        <div className="artist-identity">
          {enabled && (
            <img
              className={`artist-logo${logo ? " is-loaded" : ""}`}
              src={logoSrc}
              alt=""
              onLoad={() => setLoadedLogo(logoSrc)}
              onError={() => setLoadedLogo("")}
            />
          )}
          <h1 className={logo ? "has-logo" : undefined}>{artist.name}</h1>
          {!discovered && (
            <p>
              {artist.album_count}{" "}
              {artist.album_count === 1 ? "release" : "releases"} <span>·</span>{" "}
              {artist.track_count} saved tracks
            </p>
          )}
          {!discovered && <StateBadge state="library" />}
        </div>
      </div>
    </div>
  );
}
