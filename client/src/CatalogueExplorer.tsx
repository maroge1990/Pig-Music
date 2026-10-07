import { useState } from "react";
import { api } from "./api";
import type { Track } from "./types";

type Choice = {
  id: string;
  name?: string;
  title?: string;
  description?: string;
  date?: string;
  country?: string;
};
export function CatalogueExplorer() {
  const [choices, setChoices] = useState<Choice[]>([]);
  const [stage, setStage] = useState<"artists" | "releases" | "editions">(
    "artists",
  );
  const [artist, setArtist] = useState<Choice | null>(null);
  const [parent, setParent] = useState("");
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function page(kind: "releases" | "editions", id: string, start = 0) {
    const result = await api<{
      releases?: Choice[];
      editions?: Choice[];
      total: number;
    }>(
      `/v1/catalogue/${kind === "releases" ? "artists" : "groups"}/${id}/${kind}?offset=${start}`,
    );
    setChoices(result.releases || result.editions || []);
    setTotal(result.total);
    setOffset(start);
    setParent(id);
    setStage(kind);
    setTracks([]);
  }
  async function request(values: Track[]) {
    await api("/v1/requests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tracks: values.map((t) => ({
          title: t.title,
          artist: t.artist,
          album: t.album,
          album_artist: t.album_artist,
          year: String(t.year || ""),
          duration: t.duration,
          disc_number: t.disc_number,
          track_number: t.track_number,
          musicbrainz_release_id: t.musicbrainz_release_id,
          musicbrainz_recording_id: t.musicbrainz_recording_id,
        })),
      }),
    });
    setMessage("Added or requested for your library");
    window.dispatchEvent(new Event("music-library-changed"));
  }
  return (
    <section className="account-section">
      <h2>Discover music</h2>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const query = new FormData(e.currentTarget).get("artist");
          void run(async () => {
            const data = await api<{ artists: Choice[] }>(
              "/v1/catalogue/artists?q=" + encodeURIComponent(String(query)),
            );
            setChoices(data.artists);
            setStage("artists");
            setArtist(null);
            setTracks([]);
            setTotal(0);
          });
        }}
      >
        <label>
          Artist name
          <input
            name="artist"
            type="search"
            required
            minLength={2}
            maxLength={150}
          />
        </label>
        <button disabled={busy}>Search catalogue</button>
      </form>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
      {artist && (
        <>
          <h3>{artist.name}</h3>
          <p>
            Choose an edition to request its music, or follow future releases.
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await api(`/v1/artists/${artist.id}/acquisition`, {
                  method: "PUT",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    kinds: ["album"],
                    monitor: true,
                    request: false,
                  }),
                });
                setMessage("Following future albums for your library");
              })
            }
          >
            Follow new albums
          </button>
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                await api(`/v1/artists/${artist.id}/acquisition`, {
                  method: "DELETE",
                });
                setMessage("Stopped following this artist");
              })
            }
          >
            Stop following
          </button>
        </>
      )}
      {tracks.length > 0 ? (
        <>
          <h3>{title}</h3>
          <button
            disabled={busy}
            onClick={() => void run(() => request(tracks))}
          >
            Request this edition
          </button>
          {tracks.map((t) => (
            <article className="personal-track" key={t.id}>
              <div>
                <strong>{t.title}</strong>
                <p>
                  {t.artist} ·{" "}
                  {t.server_state === "household_available"
                    ? "On server"
                    : t.server_state === "in_library"
                      ? "In your library"
                      : "Catalogue"}
                </p>
              </div>
              <button
                disabled={busy || t.server_state === "in_library"}
                onClick={() => void run(() => request([t]))}
              >
                {t.server_state === "household_available"
                  ? "Add to my library"
                  : "Request"}
              </button>
            </article>
          ))}
        </>
      ) : (
        <>
          {choices.map((choice) => (
            <p key={choice.id}>
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    if (stage === "artists") {
                      setArtist(choice);
                      await page("releases", choice.id);
                    } else if (stage === "releases")
                      await page("editions", choice.id);
                    else {
                      const data = await api<{
                        title: string;
                        tracks: Track[];
                      }>(`/v1/catalogue/releases/${choice.id}`);
                      setTracks(data.tracks);
                      setTitle(data.title);
                    }
                  })
                }
              >
                {choice.name || choice.title} {choice.date} {choice.country}
              </button>
              {choice.description && <span> · {choice.description}</span>}
            </p>
          ))}
          {total > 50 && stage !== "artists" && (
            <nav aria-label="Catalogue pages">
              <button
                disabled={offset === 0 || busy}
                onClick={() => void run(() => page(stage, parent, offset - 50))}
              >
                Previous
              </button>
              <span>
                {offset + 1}–{Math.min(offset + 50, total)} of {total}
              </span>
              <button
                disabled={offset + 50 >= total || busy}
                onClick={() => void run(() => page(stage, parent, offset + 50))}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}
