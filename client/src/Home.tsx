import { useEffect, useState } from "react";
import { api } from "./api";
import { Cover, catalogueCover } from "./Cover";
import { discoverUrl } from "./navigation";
type Item = {
  id: string;
  name: string;
  artist: string;
  artist_id: string;
  release_id?: string;
  reason?: string;
  kind: string;
};
type Feed = {
  artists: Item[];
  albums: Item[];
  songs: Item[];
  source: string;
  unavailable: boolean;
};
function HomeSection({ kind }: { kind: "popular" | "recommended" }) {
  const [feed, setFeed] = useState<Feed | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void api<Feed>("/v1/home/" + kind, { signal: controller.signal })
      .then(setFeed)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [kind]);
  return (
    <section className="home-section">
      <h2>
        {kind === "popular" ? "Popular this week" : "Recommended for you"}
      </h2>
      <p>
        {feed?.source ||
          (kind === "popular"
            ? "ListenBrainz listeners"
            : "Based on artists saved in your library")}
      </p>
      {!feed && <p role="status">{error || "Finding music…"}</p>}
      {feed &&
        ["artists", "albums", "songs"].map((collection) => (
          <section key={collection}>
            <h3>{collection[0].toUpperCase() + collection.slice(1)}</h3>
            <div className="home-grid">
              {feed[collection as "artists"].map((item) => (
                <button
                  className="album-card"
                  key={item.id}
                  onClick={() => {
                    location.hash =
                      discoverUrl(
                        { id: item.artist_id, name: item.artist || item.name },
                        collection === "songs" ? item.release_id : undefined,
                      ) + (collection === "albums" ? "&group=" + item.id : "");
                  }}
                >
                  <Cover
                    title={item.name}
                    artist={collection === "artists"}
                    src={
                      collection === "artists"
                        ? `/api/catalogue/artists/${item.id}/artwork`
                        : collection === "albums"
                          ? catalogueCover("release-group", item.id)
                          : item.release_id
                            ? catalogueCover("release", item.release_id)
                            : undefined
                    }
                  />
                  <strong>{item.name}</strong>
                  <p>{collection !== "artists" && item.artist}</p>
                  {item.reason && <small>{item.reason}</small>}
                </button>
              ))}
            </div>
            {!feed[collection as "artists"].length && (
              <p className="muted">
                {kind === "recommended"
                  ? "Save artists to your library to find related music. Some artists do not yet have similarity data."
                  : "This feed is temporarily unavailable."}
              </p>
            )}
          </section>
        ))}
      {feed?.unavailable && (
        <p role="status">
          Some discovery feeds are unavailable. Your library is still available.
        </p>
      )}
    </section>
  );
}
export function Home() {
  return (
    <main className="personal-main home-page">
      <h1>Home</h1>
      <p>Find your next favourite.</p>
      <HomeSection kind="popular" />
      <HomeSection kind="recommended" />
    </main>
  );
}
