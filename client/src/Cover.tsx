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
}: {
  title: string;
  src?: string | null;
  artist?: boolean;
  className?: string;
}) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [src]);
  return (
    <div className={`cover ${artist ? "artist-cover" : ""} ${className}`}>
      {src && !broken ? (
        <img
          src={src}
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
