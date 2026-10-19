import { useEffect, useState } from "react";

export function catalogueCover(kind: "release" | "release-group", id: string) {
  return `/api/v1/catalogue/artwork/${kind}/${encodeURIComponent(id)}`;
}

/** A catalogue artist's portrait, for search results and artist pages. */
export function catalogueArtistCover(id: string) {
  return `/api/v1/catalogue/artists/${encodeURIComponent(id)}/artwork`;
}

/** The exact address a cover requests at one width; pre-caching uses it too. */
export function coverUrl(src: string, width: number, revision = 0) {
  if (!src.startsWith("/api/v1/")) return src;
  const url = new URL(src, window.location.origin);
  url.searchParams.set("w", String(width));
  url.searchParams.set("v", "1");
  if (!src.startsWith("/api/v1/covers/"))
    url.searchParams.set("r", String(revision));
  return url.pathname + url.search;
}

export function Cover({
  title,
  src,
  artist = false,
  className = "",
  sizes = "(max-width: 480px) 50vw, (max-width: 600px) 33vw, (max-width: 1200px) 25vw, 200px",
}: {
  title: string;
  src?: string | null;
  artist?: boolean;
  className?: string;
  sizes?: string;
}) {
  const [broken, setBroken] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const changed = () => {
      setBroken(false);
      setRevision((r) => r + 1);
    };
    window.addEventListener("music-artwork-changed", changed);
    return () => window.removeEventListener("music-artwork-changed", changed);
  }, []);
  // The server fetches missing artwork in the background: look again soon,
  // then fall back to the shared slow retry clock.
  const [attempts, setAttempts] = useState(0);
  useEffect(() => {
    if (!broken) return;
    const retry = () => {
      setBroken(false);
      setRevision((r) => r + 1);
    };
    const soon =
      attempts < 2
        ? setTimeout(() => {
            setAttempts((n) => n + 1);
            retry();
          }, [2000, 6000][attempts])
        : undefined;
    window.addEventListener("music-artwork-retry", retry);
    return () => {
      clearTimeout(soon);
      window.removeEventListener("music-artwork-retry", retry);
    };
  }, [broken]);
  const image = (width: number) => coverUrl(src || "", width, revision);
  useEffect(() => {
    setBroken(false);
    setAttempts(0);
  }, [src]);
  return (
    <div className={`cover ${artist ? "artist-cover" : ""} ${className}`}>
      {src && !broken ? (
        <img
          src={image(512)}
          srcSet={
            src.startsWith("/api/v1/")
              ? [128, 256, 512, 1024].map((w) => `${image(w)} ${w}w`).join(", ")
              : undefined
          }
          sizes={sizes}
          alt=""
          loading="lazy"
          decoding="async"
          referrerPolicy="no-referrer"
          onError={() => setBroken(true)}
        />
      ) : (
        <>
          <span className="placeholder-halo" aria-hidden="true" />
          <span className="cover-initials" aria-hidden="true">
            {title
              .split(" ")
              .filter(Boolean)
              .slice(0, 2)
              .map((w) => w[0])
              .join("")}
          </span>
        </>
      )}
    </div>
  );
}
