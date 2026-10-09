import { lazy, Suspense } from "react";
import { HardDrive, CircleCheck, ShieldCheck } from "lucide-react";
import type { Library } from "./types";
import { QualitySettings } from "./QualitySettings";
import { QualitySelect } from "./QualitySelect";
import { sourceIds, sourceName, sources } from "./sources";
import { LibraryScan } from "./LibraryScan";
import { ToolBoundary } from "./ToolBoundary";
const Organisation = lazy(() =>
  import("./Organisation").then((m) => ({ default: m.Organisation })),
);
const RemovedMusic = lazy(() =>
  import("./RemovedMusic").then((m) => ({ default: m.RemovedMusic })),
);
export type DownloadSettings = {
  enabled: boolean;
  profile: string;
  sources: string[];
  concurrent_downloads: number;
  fallback_profile: string;
  fallback_minutes: number;
  recheck_hours: number;
};

type Health = { configured: boolean; connected: boolean } | null;

export function SystemStatus({
  library,
  downloadSettings,
  soulseekHealth,
  publicOrigin,
}: {
  library: Library | null;
  downloadSettings: DownloadSettings | null;
  soulseekHealth: Health;
  /** undefined while loading, null when none is configured. */
  publicOrigin?: string | null;
}) {
  return (
    <>
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
            <dt>Last scan</dt>
            <dd>
              {library?.snapshot.captured_at
                ? new Intl.DateTimeFormat("en-AU", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(library.snapshot.captured_at))
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
          <span className="status-pill neutral-pill">Direct SMB storage</span>
          <dl>
            <dt>Downloads</dt>
            <dd>{downloadSettings?.enabled ? "Enabled" : "Paused"}</dd>
            <dt>Tagging & renaming</dt>
            <dd>Existing artist / album folders</dd>
            <dt>Migration &amp; queue</dt>
            <dd>Saved locally</dd>
            <dt>Public address</dt>
            <dd>
              {publicOrigin === undefined
                ? "Checking…"
                : publicOrigin
                  ? new URL(publicOrigin).host
                  : "Not configured"}
            </dd>
          </dl>
          <p>
            Downloads are validated and tagged before publication into your SMB
            library. Plex playlists update as songs become available.
          </p>
        </section>
      </div>
    </>
  );
}

export function DownloadSettingsPanel({
  downloadSettings,
  setDownloadSettings,
  busy,
  save,
  soulseekHealth,
}: {
  soulseekHealth: Health;
  downloadSettings: DownloadSettings;
  setDownloadSettings: (value: DownloadSettings) => void;
  busy: boolean;
  save: () => void;
}) {
  return (
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
        Files download directly to SMB and publish into your existing artist and
        album folders. Quality is checked on the actual file; quality changes
        always download a new source file and never convert existing files.
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
        Household default quality
        <QualitySelect
          ariaLabel="Download quality"
          value={downloadSettings.profile}
          onChange={(profile) =>
            setDownloadSettings({ ...downloadSettings, profile })
          }
        />
      </label>
      <p className="status-text">
        Lossless files are only available from Soulseek; other sources are used
        for lower qualities.
      </p>
      {sourceIds.map((source) => (
        <label className="download-option source-option" key={source}>
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
          {sourceName(source)}
          <small>{sources[source].description}</small>
        </label>
      ))}
      <QualitySettings
        value={downloadSettings}
        onChange={(value) =>
          setDownloadSettings({ ...downloadSettings, ...value })
        }
      />
      <button className="primary-button" disabled={busy} onClick={save}>
        Save download settings
      </button>
    </section>
  );
}

export function ServerLibraryTools({
  library,
  refresh,
  setToast,
}: {
  library: Library | null;
  refresh: () => void;
  setToast: (message: string) => void;
}) {
  return (
    <>
      <LibraryScan refresh={refresh} />
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
