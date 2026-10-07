import { lazy, Suspense } from "react";
import type { Dispatch, SetStateAction } from "react";
import { HardDrive, CircleCheck, ShieldCheck } from "lucide-react";
import type { Library } from "./types";
import { MediaSettings } from "./MediaSettings";
import { QualitySettings } from "./QualitySettings";
import { LibraryScan } from "./LibraryScan";
import { ToolBoundary } from "./ToolBoundary";
const Organisation = lazy(() =>
  import("./Organisation").then((m) => ({ default: m.Organisation })),
);
const RemovedMusic = lazy(() =>
  import("./RemovedMusic").then((m) => ({ default: m.RemovedMusic })),
);
export type Appearance = "system" | "light" | "dark";

export type DownloadSettings = {
  enabled: boolean;
  profile: string;
  sources: string[];
  concurrent_downloads: number;
  fallback_profile: string;
  fallback_minutes: number;
  recheck_hours: number;
};

type Props = {
  appearance: Appearance;
  setAppearance: Dispatch<SetStateAction<Appearance>>;
  library: Library | null;
  downloadSettings: DownloadSettings | null;
  setDownloadSettings: Dispatch<SetStateAction<DownloadSettings | null>>;
  soulseekHealth: { configured: boolean; connected: boolean } | null;
  busy: boolean;
  saveDownloads: () => void;
  setToast: (message: string) => void;
  refresh: () => void;
};
export function SystemView({
  appearance,
  setAppearance,
  library,
  downloadSettings,
  setDownloadSettings,
  soulseekHealth,
  busy,
  saveDownloads,
  setToast,
  refresh,
}: Props) {
  return (
    <>
      <div className="page-heading">
        <h1>Settings</h1>
      </div>
      <div className="appearance-control">
        <label htmlFor="appearance">Appearance</label>
        <select
          id="appearance"
          value={appearance}
          onChange={(e) => setAppearance(e.target.value as Appearance)}
        >
          <option value="system">System default</option>
          <option value="light">Light</option>
          <option value="dark">Dark</option>
        </select>
        <span>
          Saved on this device. System default follows your device appearance.
        </span>
      </div>
      <div className="system-grid">
        <section className="system-panel">
          <HardDrive />
          <h2>Synology library</h2>
          <span className="status-pill">
            <CircleCheck size={13} /> Local snapshot ready
          </span>
          <dl>
            <dt>Source</dt>
            <dd>{library?.snapshot.source || "No snapshot loaded"}</dd>
            <dt>Captured</dt>
            <dd>
              {library?.snapshot.captured_at
                ? new Date(library.snapshot.captured_at).toLocaleString()
                : "Not yet"}
            </dd>
            <dt>Indexed tracks</dt>
            <dd>{library?.stats.tracks.toLocaleString()}</dd>
            <dt>Tag read issues</dt>
            <dd>{library?.snapshot.read_failures?.length || 0}</dd>
          </dl>
          <p>
            Browsing uses a local snapshot. Use Scan library to pick up changes
            made outside Pig Music.
          </p>
        </section>
        <section className="system-panel">
          <ShieldCheck />
          <h2>Library storage</h2>
          <span className="status-pill preview-pill">Direct SMB storage</span>
          <dl>
            <dt>Downloads</dt>
            <dd>{downloadSettings?.enabled ? "Enabled" : "Paused"}</dd>
            <dt>Tagging & renaming</dt>
            <dd>Existing artist / album folders</dd>
            <dt>Migration &amp; queue</dt>
            <dd>Saved locally</dd>
            <dt>Remote access</dt>
            <dd>Existing Tailscale connection</dd>
          </dl>
          <p>
            Downloads are validated and tagged before publication into your SMB
            library. Plex playlists update as songs become available.
          </p>
        </section>
      </div>
      {downloadSettings && (
        <section className="system-panel download-panel">
          <h2>Download settings</h2>
          <p className="status-text">
            Soulseek engine:{" "}
            {soulseekHealth
              ? soulseekHealth.connected
                ? "Connected"
                : soulseekHealth.configured
                  ? "Unavailable"
                  : "Not configured"
              : "Checking connection…"}
          </p>
          <p>
            Files download directly to SMB and publish into your existing artist
            and album folders. Quality is checked on the actual file; quality
            changes always download a new source file and never convert existing
            files.
          </p>
          <label className="download-option">
            <input
              type="checkbox"
              checked={downloadSettings.enabled}
              onChange={(e) =>
                setDownloadSettings({
                  ...downloadSettings,
                  enabled: e.target.checked,
                })
              }
            />
            Enable downloads
          </label>
          <label className="download-option">
            Quality
            <select
              aria-label="Download quality"
              value={downloadSettings.profile}
              onChange={(e) =>
                setDownloadSettings({
                  ...downloadSettings,
                  profile: e.target.value,
                })
              }
            >
              <option value="mp3_320">MP3 320 kbps</option>
              <option value="mp3_128">MP3 128 kbps</option>
              <option value="aac_256">AAC 256 kbps or better</option>
              <option value="lossless">FLAC lossless (Soulseek)</option>
            </select>
          </label>
          {["soulseek", "freemp3cloud", "zvu4no", "jiosaavn"].map((source) => (
            <label className="download-option" key={source}>
              <input
                type="checkbox"
                checked={downloadSettings.sources.includes(source)}
                onChange={(e) =>
                  setDownloadSettings({
                    ...downloadSettings,
                    sources: e.target.checked
                      ? [...downloadSettings.sources, source]
                      : downloadSettings.sources.filter((s) => s !== source),
                  })
                }
              />
              {source}
            </label>
          ))}
          <QualitySettings
            value={downloadSettings}
            onChange={(value) =>
              setDownloadSettings({ ...downloadSettings, ...value })
            }
          />
          <button
            className="primary-button"
            disabled={busy}
            onClick={saveDownloads}
          >
            Save download settings
          </button>
        </section>
      )}
      <LibraryScan refresh={refresh} />
      <MediaSettings />
      <ToolBoundary>
        <Suspense fallback={<p>Loading library tools…</p>}>
          <RemovedMusic notify={setToast} />
          <Organisation notify={setToast} />
        </Suspense>
      </ToolBoundary>
      {!!library?.snapshot.read_failures?.length && (
        <>
          <div className="section-title">
            <h2>Files needing attention</h2>
          </div>
          <div className="read-issues">
            {library.snapshot.read_failures.slice(0, 30).map((f) => (
              <div key={f.path}>
                <strong>{f.path}</strong>
                <span>{f.error}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
