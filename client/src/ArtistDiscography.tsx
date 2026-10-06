import { apiFetch as fetch } from "./api";
import { useEffect, useState } from "react";
import { ArtistAcquisition } from "./ArtistAcquisition";
import { CatalogueBrowser } from "./CatalogueBrowser";
export function ArtistDiscography({
  id,
  notify,
}: {
  id: string;
  notify: (message: string) => void;
}) {
  const [artist, setArtist] = useState<{ id: string; name: string } | null>(
    null,
  );
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/artists/${id}/catalogue`, { signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : "Discography unavailable.",
          );
        return data;
      })
      .then(setArtist)
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      });
    return () => controller.abort();
  }, [id]);
  return (
    <section className="artist-discography">
      {artist ? (
        <>
          <CatalogueBrowser
            artist={artist}
            close={() => {}}
            notify={notify}
            embedded
          />
          <ArtistAcquisition id={artist.id} notify={notify} />
        </>
      ) : (
        <p className={error ? "inline-error" : "muted"}>
          {error || "Finding this artist’s discography…"}
        </p>
      )}
    </section>
  );
}
