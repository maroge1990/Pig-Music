import { apiFetch } from "./api";
import { useEffect, useState } from "react";
export function AlbumQuality({
  id,
  notify,
  kind = "album",
  embedded = false,
}: {
  id: string;
  notify: (message: string) => void;
  kind?: "album" | "artist";
  embedded?: boolean;
}) {
  const [profile, setProfile] = useState("");
  const [effective, setEffective] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const path = `/api/${kind === "album" ? "albums" : "artists"}/${id}/quality`;
  useEffect(() => {
    const controller = new AbortController();
    void apiFetch(path, { signal: controller.signal })
      .then((r) => r.json())
      .then((data) => {
        if (!controller.signal.aborted) {
          setProfile(data.profile || "");
          setEffective(data.effective_profile);
        }
      })
      .catch(() => {});
    return () => controller.abort();
  }, [path]);
  async function apply() {
    setBusy(true);
    setError("");
    try {
      const response = await apiFetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ profile: profile || null }),
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Quality preference unavailable.",
        );
      const updated = await apiFetch(path).then((r) => r.json());
      setEffective(updated.effective_profile);
      notify(
        `${data.created} replacements queued${data.downloads_enabled ? "" : " · downloads paused"}. Existing music stays until replacement succeeds.`,
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const content = (
    <>
      {!embedded && (
        <summary>
          {kind === "album" ? "Album" : "Artist"} quality preference
          {effective
            ? ` · ${effective === "lossless" ? "FLAC" : effective.replace("_", " ")}`
            : ""}
        </summary>
      )}
      <p>
        Album preference takes precedence over artist preference, then the
        system default. Changing quality re-downloads matching source files; it
        never converts your music. The previous download is removed only after a
        validated replacement succeeds.
      </p>
      <div className="release-actions">
        <label>
          Preferred quality
          <select
            aria-label={`${kind === "album" ? "Album" : "Artist"} preferred quality`}
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
          >
            <option value="">
              {kind === "album"
                ? "Use artist / system preference"
                : "Use system preference"}
            </option>
            <option value="lossless">FLAC lossless</option>
            <option value="mp3_320">MP3 320 kbps</option>
            <option value="aac_256">AAC 256 kbps</option>
            <option value="mp3_128">MP3 128 kbps</option>
          </select>
        </label>
        <button className="secondary-button" disabled={busy} onClick={apply}>
          Apply preference &amp; re-download
        </button>
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
  return embedded ? (
    <div>{content}</div>
  ) : (
    <details className="album-quality">{content}</details>
  );
}
