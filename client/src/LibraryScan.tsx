import { apiFetch } from "./api";
import { useEffect, useState } from "react";
type Scan = {
  status?: string;
  files?: number;
  missing?: number;
  read_failures?: number;
  error?: string;
};
export function LibraryScan({ refresh }: { refresh: () => void }) {
  const [scan, setScan] = useState<Scan>({});
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    let previous = "";
    const update = () =>
      apiFetch("/api/library/scan")
        .then((r) => r.json())
        .then((v) => {
          if (!active) return;
          setScan(v);
          if (previous === "scanning" && v.status === "completed") refresh();
          previous = v.status;
        })
        .catch(() => {});
    void update();
    const timer = setInterval(
      () => {
        if (!document.hidden) void update();
      },
      scan.status === "scanning" ? 3000 : 30000,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [scan.status]);
  async function start() {
    setError("");
    try {
      const r = await apiFetch("/api/library/scan", { method: "POST" });
      const value = await r.json();
      if (!r.ok) throw new Error(value.detail || "Scan unavailable.");
      setScan(value);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section className="system-panel">
      <h2>Library scan</h2>
      <p>
        Read tags and artwork from your configured music folder. Existing files
        are left unchanged.
      </p>
      <button
        className="secondary-button"
        disabled={scan.status === "scanning"}
        onClick={() => void start()}
      >
        {scan.status === "scanning"
          ? `Scanning · ${scan.files || 0} files`
          : "Scan library"}
      </button>
      {scan.status === "completed" && (
        <p>
          {scan.files} files indexed
          {scan.missing ? ` · ${scan.missing} unavailable` : ""}
          {scan.read_failures ? ` · ${scan.read_failures} need attention` : ""}
        </p>
      )}
      {(error || scan.error) && <p role="alert">{error || scan.error}</p>}
    </section>
  );
}
