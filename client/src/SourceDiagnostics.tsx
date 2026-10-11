import { useEffect, useState } from "react";
import { api } from "./api";
import { formatDateTime } from "./format";

type Status = {
  id: string;
  name: string;
  profiles: string[];
  configured: boolean;
  enabled: boolean;
  session_configured: boolean;
  metadata_reachable: boolean | null;
  last_transfer: string | null;
  last_transfer_at: number | null;
  reason: string | null;
  next_retry_at: number | null;
};
const root = "/v1/admin/download-sources";
export function SourceDiagnostics() {
  const [sources, setSources] = useState<Status[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const refresh = () => api<Status[]>(root).then(setSources);
  useEffect(() => {
    let active = true;
    api<Status[]>(root)
      .then((value) => active && setSources(value))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  async function action(work: () => Promise<unknown>) {
    setBusy(true);
    setMessage("");
    try {
      await work();
      await refresh();
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Source check failed",
      );
      await refresh().catch(() => {});
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>Source diagnostics and YouTube session</summary>
      <p>
        Metadata checks do not download audio. Audio is marked verified only
        after a complete recording passes validation. Temporary source failures
        allow other sources to continue.
      </p>
      {sources.map((source) => (
        <div className="source-diagnostic" key={source.id}>
          <strong>{source.name}</strong>
          <p>
            {!source.configured
              ? "Setup required"
              : source.metadata_reachable === null
                ? "Metadata not checked"
                : source.metadata_reachable
                  ? "Metadata reachable"
                  : "Metadata unavailable"}
            {" · "}
            {source.last_transfer === "verified"
              ? "Last audio transfer verified"
              : source.last_transfer === "failed"
                ? "Last audio transfer failed"
                : "Audio transfer not verified"}
          </p>
          {source.reason && <p>{source.reason}</p>}
          {!!source.next_retry_at && (
            <p>Retry after {formatDateTime(source.next_retry_at)}</p>
          )}
          <button
            disabled={busy || !source.configured}
            onClick={() =>
              void action(() =>
                api(`${root}/${source.id}/check`, { method: "POST" }),
              )
            }
          >
            Check {source.name} metadata
          </button>
        </div>
      ))}
      <p>
        YouTube can work anonymously. If access is required, upload a Netscape
        cookie file containing only YouTube and Google cookies. Session data
        stays on the server; removing it makes future operations anonymous.
      </p>
      <label className="download-option">
        YouTube cookie file
        <input
          aria-label="YouTube cookie file"
          type="file"
          accept=".txt"
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            if (file.size > 262144) {
              setMessage("Choose a cookie file smaller than 256 KiB");
              return;
            }
            void action(async () =>
              api(`${root}/youtube/cookies`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cookies: await file.text() }),
              }),
            );
          }}
        />
      </label>
      <p>
        {sources.find((source) => source.id === "youtube")?.session_configured
          ? "YouTube session configured"
          : "YouTube uses anonymous access"}
      </p>
      <button
        disabled={busy}
        onClick={() =>
          void action(() =>
            api(`${root}/youtube/cookies`, { method: "DELETE" }),
          )
        }
      >
        Remove YouTube session
      </button>
      <p role="status" aria-live="polite">
        {busy ? "Checking source…" : message}
      </p>
    </details>
  );
}
