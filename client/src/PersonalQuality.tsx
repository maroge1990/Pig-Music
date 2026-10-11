import { useEffect, useState } from "react";
import { api } from "./api";
import {
  QualitySelect,
  qualityLabel,
  type QualityOption,
} from "./QualitySelect";
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
  const [options, setOptions] = useState<QualityOption[] | undefined>();
  const [fallback, setFallback] = useState("");
  useEffect(() => {
    void api<{
      preferences: { scope: string; item_id: string; preferred: string }[];
      options: QualityOption[];
      household_default: string;
    }>("/v1/quality")
      .then((d) => {
        setOptions(d.options);
        setFallback(
          d.preferences.find((p) => p.scope === "system")?.preferred ||
            d.household_default,
        );
        setPreferred(
          d.preferences.find((p) => p.scope === scope && p.item_id === itemId)
            ?.preferred || "",
        );
      })
      .catch((e) => setMessage(e.message));
  }, [scope, itemId]);
  function save(value: string) {
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
          "Saved. Shared files keep the highest quality anyone wants.",
        );
        window.dispatchEvent(new Event("music-library-changed"));
      })
      .catch((e) => setMessage(e.message))
      .finally(() => setBusy(false));
  }
  return (
    <div className="quality-inline">
      <QualitySelect
        label="Quality"
        value={preferred}
        options={options}
        disabled={busy}
        onChange={save}
        inheritLabel={
          scope === "artist"
            ? `Use your default${fallback ? ` (${qualityLabel(fallback, options)})` : ""}`
            : "Use artist or your default"
        }
      />
      {message && <small role="status">{message}</small>}
    </div>
  );
}
