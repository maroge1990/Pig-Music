import { useEffect, useState } from "react";
import { api } from "./api";
export function PersonalQuality({
  scope,
  itemId,
}: {
  scope: "artist" | "album";
  itemId: string;
}) {
  const [preferred, setPreferred] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api<{
      preferences: { scope: string; item_id: string; preferred: string }[];
    }>("/v1/quality")
      .then((d) =>
        setPreferred(
          d.preferences.find((p) => p.scope === scope && p.item_id === itemId)
            ?.preferred || "",
        ),
      )
      .catch((e) => setMessage(e.message));
  }, [scope, itemId]);
  return (
    <section className="account-section">
      <label>
        Quality for this {scope}
        <select
          value={preferred}
          disabled={busy}
          onChange={(e) => {
            const value = e.target.value;
            setBusy(true);
            void api("/v1/quality", {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                scope,
                item_id: itemId,
                preferred: value || null,
              }),
            })
              .then(() => {
                setPreferred(value);
                setMessage(
                  "Preference saved. Shared files retain the highest quality wanted by their members.",
                );
                window.dispatchEvent(new Event("music-library-changed"));
              })
              .catch((e) => setMessage(e.message))
              .finally(() => setBusy(false));
          }}
        >
          <option value="">Use my general preference</option>
          <option value="mp3_128">MP3 128</option>
          <option value="mp3_320">MP3 320</option>
          <option value="aac_256">AAC 256</option>
          <option value="lossless">Lossless</option>
          <option value="native_standard">
            Native audio — standard or better
          </option>
        </select>
      </label>
      {message && <p role="status">{message}</p>}
    </section>
  );
}
