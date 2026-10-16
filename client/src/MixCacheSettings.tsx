import { useEffect, useState } from "react";
import { api } from "./api";
import { formatCount } from "./format";
import { QualitySelect, defaultQualityOptions } from "./QualitySelect";

type Settings = {
  budget_bytes: number;
  reserve_bytes: number;
  profile: string;
  timezone: string;
  files: number;
  used_bytes: number;
  ready: number;
  preparing: number;
  retrying: number;
  failed?: number;
  reclaimable_bytes?: number;
  issues?: { mix: string; person?: string; message: string }[];
};
export function MixCacheSettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    void api<Settings>("/v1/admin/mixes", { signal: controller.signal })
      .then(setSettings)
      .catch((e) => {
        if (!controller.signal.aborted) setNotice(e.message);
      });
    return () => controller.abort();
  }, []);
  return (
    <section className="system-panel">
      <h2>Mix preparation</h2>
      {settings && (
        <>
          <p>
            {formatCount(settings.files)} cached songs ·{" "}
            {formatCount(Math.round(settings.used_bytes / 1_000_000))} MB used
          </p>
          <p>
            {formatCount(settings.ready)} ready mixes ·{" "}
            {formatCount(settings.preparing)} preparing ·{" "}
            {formatCount(settings.retrying)} retrying ·{" "}
            {formatCount(settings.failed ?? 0)} unavailable candidates
          </p>
          <p>
            {formatCount(
              Math.round((settings.reclaimable_bytes ?? 0) / 1_000_000),
            )}{" "}
            MB can be reclaimed. Active editions and playing queues stay
            protected.
          </p>
          <button
            disabled={busy}
            onClick={() => {
              setBusy(true);
              void api<Settings>("/v1/admin/mixes")
                .then((value) =>
                  setSettings((current) =>
                    current
                      ? {
                          ...current,
                          files: value.files,
                          used_bytes: value.used_bytes,
                          ready: value.ready,
                          preparing: value.preparing,
                          retrying: value.retrying,
                          failed: value.failed,
                          reclaimable_bytes: value.reclaimable_bytes,
                          issues: value.issues,
                        }
                      : value,
                  ),
                )
                .catch((e) => setNotice(e.message))
                .finally(() => setBusy(false));
            }}
          >
            Refresh mix status
          </button>
          {!!settings.issues?.length && (
            <details>
              <summary>Preparation issues</summary>
              <ul>
                {settings.issues.map((issue, index) => (
                  <li key={index}>
                    <strong>
                      {issue.person && `${issue.person} · `}
                      {issue.mix}:
                    </strong>{" "}
                    {issue.message}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setBusy(true);
              void api<Settings>("/v1/admin/mixes", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  budget_bytes: settings.budget_bytes,
                  reserve_bytes: settings.reserve_bytes,
                  profile: settings.profile,
                  timezone: settings.timezone,
                }),
              })
                .then((value) => {
                  setSettings(value);
                  setNotice("Mix preparation settings saved.");
                })
                .catch((e) => setNotice(e.message))
                .finally(() => setBusy(false));
            }}
          >
            <label>
              Cache budget (GB)
              <input
                type="number"
                min="1"
                max="2000"
                required
                value={settings.budget_bytes / 1_000_000_000}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    budget_bytes: Number(e.target.value) * 1_000_000_000,
                  })
                }
              />
            </label>
            <label>
              Keep disk space free (GB)
              <input
                type="number"
                min="1"
                max="100"
                required
                value={settings.reserve_bytes / 1_000_000_000}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    reserve_bytes: Number(e.target.value) * 1_000_000_000,
                  })
                }
              />
            </label>
            <QualitySelect
              label="Preferred cache quality"
              value={settings.profile}
              onChange={(profile) => setSettings({ ...settings, profile })}
              options={defaultQualityOptions.filter((o) =>
                ["mp3_320", "native_standard", "lossless"].includes(o.value),
              )}
            />
            <label>
              Daily rotation timezone
              <input
                required
                value={settings.timezone}
                onChange={(e) =>
                  setSettings({ ...settings, timezone: e.target.value })
                }
              />
            </label>
            <p>
              Uses enabled download sources and pauses when server downloads are
              paused. Active mixes stay protected when the budget is full.
              Preferred lossless may fall back to MP3, then AAC when enabled.
            </p>
            <button disabled={busy}>Save preparation settings</button>
          </form>
        </>
      )}
      {notice && <p role="status">{notice}</p>}
    </section>
  );
}
