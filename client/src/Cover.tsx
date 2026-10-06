import { useEffect, useState } from "react";
import { Disc3 } from "lucide-react";

export function catalogueCover(kind: "release" | "release-group", id: string) {
  return `/api/catalogue/artwork/${kind}/${encodeURIComponent(id)}`;
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
  useEffect(() => {
    if (!broken) return;
    const retry = () => {
      setBroken(false);
      setRevision((r) => r + 1);
    };
    window.addEventListener("music-artwork-retry", retry);
    return () => window.removeEventListener("music-artwork-retry", retry);
  }, [broken]);
  const image = (width: number) => {
    if (!src?.startsWith("/api/")) return src || "";
    const url = new URL(src, window.location.origin);
    url.searchParams.set("w", String(width));
    url.searchParams.set("v", "1");
    if (!src.startsWith("/api/artwork/"))
      url.searchParams.set("r", String(revision));
    return url.pathname + url.search;
  };
  useEffect(() => setBroken(false), [src]);
  return (
    <div className={`cover ${artist ? "artist-cover" : ""} ${className}`}>
      {src && !broken ? (
        <img
          src={image(512)}
          srcSet={
            src.startsWith("/api/")
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
          <Disc3 className="placeholder-disc" />
          <span className="cover-initials">
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
