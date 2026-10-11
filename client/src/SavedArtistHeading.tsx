import { Cover } from "./Cover";
import { ApiError, api } from "./api";
import { discoverUrl } from "./navigation";
import { useOwner } from "./person";
import type { Artist } from "./types";
import { useState } from "react";

type Candidate = { id: string; name: string; disambiguation?: string };

export function SavedArtistHeading({
  artist,
  personal = false,
}: {
  artist: Artist;
  personal?: boolean;
}) {
  const owner = useOwner();
  const [error, setError] = useState("");
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  async function open() {
    setError("");
    try {
      const identity = await api<{ id: string; name: string }>(
        personal
          ? `/v1/catalogue/library-artists/${artist.id}`
          : `/artists/${artist.id}/catalogue`,
      );
      location.hash = discoverUrl(identity);
    } catch (e) {
      const found = e instanceof ApiError ? e.body.candidates : undefined;
      if (e instanceof ApiError && e.code === "conflict" && personal) {
        setCandidates(Array.isArray(found) ? (found as Candidate[]) : []);
        return;
      }
      setError((e as Error).message);
    }
  }
  async function choose(candidate: Candidate) {
    setBusy(true);
    setError("");
    try {
      const identity = await api<{ id: string; name: string }>(
        `/v1/catalogue/library-artists/${artist.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: candidate.id }),
        },
      );
      setCandidates(null);
      location.hash = discoverUrl(identity);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="saved-artist-heading">
      <Cover title={artist.name} src={artist.cover_url} artist />
      <div>
        <span className="eyebrow">IN YOUR LIBRARY</span>
        <h1>{artist.name}</h1>
        <button className="secondary-button" onClick={() => void open()}>
          Find more by {artist.name}
        </button>
        {candidates &&
          (owner ? (
            <div
              className="artist-choice"
              role="group"
              aria-label="Choose artist"
            >
              <p>
                Several artists share this name. Choose the one in your library.
              </p>
              <ul>
                {candidates.map((candidate) => (
                  <li key={candidate.id}>
                    <span>
                      <strong>{candidate.name}</strong>
                      {candidate.disambiguation && (
                        <small> · {candidate.disambiguation}</small>
                      )}
                    </span>
                    <button
                      className="secondary-button"
                      disabled={busy}
                      onClick={() => void choose(candidate)}
                    >
                      Choose
                    </button>
                  </li>
                ))}
              </ul>
              {!candidates.length && (
                <p>No matching artists were found. Try the catalogue search.</p>
              )}
            </div>
          ) : (
            <p role="status">
              This artist shares a name with others. The owner can link it to
              the right artist.
            </p>
          ))}
        {error && <p role="alert">{error}</p>}
      </div>
    </div>
  );
}
