import { SongControls, isPending } from "./SongControls";
import { apiFetch as fetch } from "./api";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  LoaderCircle,
  ArrowDown,
  Check,
} from "lucide-react";
import { Cover, catalogueCover } from "./Cover";
import { usePlayer } from "./Player";
import { ArtistPopular } from "./ArtistPopular";
import { SongActions } from "./SongActions";
import { MusicLink } from "./MusicLink";
import { mergePage } from "./discography";
import { ArtistAcquisition } from "./ArtistAcquisition";
import { ArtistHero } from "./ArtistHero";
import { discoverUrl } from "./navigation";
import type { Discography } from "./discography";

type Group = {
  id: string;
  title: string;
  date: string;
  type: string;
  saved_album_id?: string | null;
};
type Edition = {
  id: string;
  title: string;
  date: string;
  country: string;
  description: string;
  status: string;
  formats: string[];
  track_count: number;
};
type Song = {
  id: string;
  title: string;
  artist: string;
  duration: number;
  disc_number: number;
  track_number: number;
  status: string;
  presence_note: string;
  download_status?: string;
  received_bytes?: number;
  total_bytes?: number;
};
type Release = {
  id: string;
  title: string;
  artist: string;
  date: string;
  description: string;
  tracks: Song[];
};
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api/catalogue/" + path, options);
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : "Discovery unavailable. Try again.",
    );
  return body;
}
const pending = isPending;
export function CatalogueBrowser({
  artist,
  close,
  notify,
  embedded = false,
  initialRelease,
}: {
  artist: { id: string; name: string };
  close: () => void;
  notify: (text: string) => void;
  embedded?: boolean;
  initialRelease?: string;
}) {
  const player = usePlayer();
  const [kind, setKind] = useState("album");
  const scope = artist.id + ":" + kind;
  const [listing, setListing] = useState<Discography>({
    scope,
    groups: [],
    total: 0,
    loading: true,
  });
  const [visible, setVisible] = useState(100);
  const groups = listing.scope === scope ? listing.groups : [];
  const total = listing.scope === scope ? listing.total : 0;
  const [group, setGroup] = useState<Group | null>(null);
  const [editions, setEditions] = useState<Edition[]>([]);
  const [editionTotal, setEditionTotal] = useState(0);
  const [release, setRelease] = useState<Release | null>(null);
  const [choose, setChoose] = useState(false);
  const [busy, setBusy] = useState(false);
  const groupBusy = listing.scope !== scope || listing.loading;
  const [error, setError] = useState("");
  const [profile, setProfile] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    const controller = new AbortController();
    setListing({ scope, groups: [], total: 0, loading: true });
    setGroup(null);
    setRelease(null);
    setError("");
    void (async () => {
      try {
        let offset = 0;
        while (!controller.signal.aborted) {
          const data = await request<{ releases: Group[]; total: number }>(
            `artists/${artist.id}/releases?kind=${kind}&offset=${offset}`,
            { signal: controller.signal },
          );
          if (controller.signal.aborted) return;
          setListing((old) =>
            controller.signal.aborted
              ? old
              : mergePage(old, scope, data.releases, data.total),
          );
          offset += data.releases.length;
          if (
            !data.releases.length ||
            offset >= data.total ||
            offset >= visible ||
            offset >= 10000
          )
            break;
        }
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        if (!controller.signal.aborted)
          setListing((old) =>
            old.scope === scope ? { ...old, loading: false } : old,
          );
      }
    })();
    return () => controller.abort();
  }, [artist.id, kind, visible]);
  useEffect(() => {
    if (!release || !release.tracks.some(pending)) return;
    const id = release.id;
    let active = true;
    const timer = setInterval(() => {
      if (document.hidden) return;
      void request<Release>(`releases/${id}`)
        .then((data) => {
          if (active) setRelease(data);
        })
        .catch(() => {});
    }, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [release?.id, release?.tracks.filter(pending).length]);
  useEffect(() => {
    if (initialRelease) {
      setGroup({ id: "", title: "Album", date: "", type: "Album" });
      void loadRelease(initialRelease);
    }
  }, [initialRelease, artist.id]);
  async function loadRelease(id: string) {
    setBusy(true);
    setError("");
    try {
      setRelease(await request<Release>(`releases/${id}`));
      if (!embedded)
        history.replaceState(null, "", "#" + discoverUrl(artist, id));
      setProfile("");
      setChoose(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function openGroup(g: Group) {
    setGroup(g);
    setRelease(null);
    setChoose(false);
    setBusy(true);
    setError("");
    try {
      const data = await request<{
        editions: Edition[];
        total: number;
        recommended_id?: string;
      }>(`groups/${g.id}/editions`);
      setEditions(data.editions);
      setEditionTotal(data.total);
      if (data.editions.length) {
        setRelease(
          await request<Release>(
            `releases/${data.recommended_id || data.editions[0].id}`,
          ),
        );
        if (!embedded)
          history.replaceState(
            null,
            "",
            "#" +
              discoverUrl(artist, data.recommended_id || data.editions[0].id),
          );
        setProfile("");
      } else setError("No release editions are available.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function moreEditions() {
    if (!group) return;
    setBusy(true);
    try {
      const data = await request<{ editions: Edition[]; total: number }>(
        `groups/${group.id}/editions?offset=${editions.length}`,
      );
      setEditions((old) => [...old, ...data.editions]);
      setEditionTotal(data.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function download(trackId?: string) {
    if (!release) return;
    const ids = trackId
      ? [trackId]
      : release.tracks
          .filter((t) => t.status !== "downloaded" && !pending(t))
          .map((t) => t.id);
    setSelected(ids);
    setBusy(true);
    setError("");
    try {
      const result = await request<{
        created: number;
        existing: number;
        skipped: number;
        downloads_enabled: boolean;
      }>(`releases/${release.id}/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          track_ids: ids,
          quality_profile: profile || null,
        }),
      });
      notify(
        `${result.created} songs queued${result.downloads_enabled ? "" : " · downloads paused"}`,
      );
      setRelease(await request<Release>(`releases/${release.id}`));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSelected([]);
      setBusy(false);
    }
  }
  function back() {
    setError("");
    if (choose) {
      setChoose(false);
    } else if (group) {
      setGroup(null);
      setRelease(null);
      if (!embedded) history.replaceState(null, "", "#" + discoverUrl(artist));
    } else close();
  }
  return (
    <section aria-label="Artist discography">
      {(group || !embedded) && (
        <button className="back-button" onClick={back} disabled={busy}>
          <ArrowLeft size={16} />
          {choose ? "Selected edition" : group ? artist.name : "Search results"}
        </button>
      )}
      {!embedded && !group && (
        <ArtistHero
          discovered
          artist={{
            ...artist,
            album_ids: [],
            album_count: 0,
            track_count: 0,
            compilation_only: false,
            cover_url: `/api/catalogue/artists/${artist.id}/artwork`,
          }}
        />
      )}
      {group && (
        <div className="page-heading catalogue-heading">
          {group && (
            <Cover
              title={release?.title || group.title}
              src={catalogueCover(
                release ? "release" : "release-group",
                release?.id || group.id,
              )}
            />
          )}
          <div>
            <div className="eyebrow">
              {release ? "ALBUM & SONGS" : "ARTIST"}
            </div>
            <h1>{release?.title || group?.title || artist.name}</h1>
            <p>
              {release ? (
                <>
                  <MusicLink artist={release.artist} /> · {release.date}{" "}
                  {release.description}
                </>
              ) : (
                "Albums first. Explore singles, EPs and other releases below."
              )}
            </p>
          </div>
        </div>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {busy && (
        <p className="subtle-loading">
          <LoaderCircle size={16} className="spin" /> Loading release…
        </p>
      )}
      {choose ? (
        <>
          <h2>Choose another edition</h2>
          {editions.map((e) => (
            <button
              className="result-row"
              key={e.id}
              disabled={busy}
              onClick={() => loadRelease(e.id)}
            >
              <Cover title={e.title} src={catalogueCover("release", e.id)} />
              <div>
                <strong>{e.title}</strong>
                <span>
                  {[
                    e.date,
                    e.country,
                    e.formats.join(" / "),
                    `${e.track_count} tracks`,
                    e.description,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </div>
              <ArrowRight size={16} />
            </button>
          ))}
          {editions.length < editionTotal && (
            <button
              className="secondary-button"
              disabled={busy}
              onClick={moreEditions}
            >
              More editions
            </button>
          )}
        </>
      ) : release ? (
        <>
          <div className="release-actions">
            <button
              className="primary-button"
              disabled={
                busy ||
                !release.tracks.some(
                  (t) => t.status !== "downloaded" && !pending(t),
                )
              }
              onClick={() => download()}
            >
              <ArrowDown size={16} />
              Download all
            </button>
          </div>
          {release.tracks.map((t) => {
            return (
              <div className="result-row catalogue-song" key={t.id}>
                <span className="song-number">{t.track_number}</span>
                <div>
                  <strong>{t.title}</strong>
                  <span>
                    {t.artist} ·{" "}
                    {t.duration
                      ? `${Math.floor(t.duration / 60)}:${String(Math.floor(t.duration % 60)).padStart(2, "0")}`
                      : ""}
                  </span>
                </div>
                <SongControls
                  song={t}
                  busy={busy}
                  selected={selected.includes(t.id)}
                  play={() =>
                    player.playCatalogue(
                      release.id,
                      t,
                      catalogueCover("release", release.id),
                    )
                  }
                  download={() => void download(t.id)}
                />
                <SongActions
                  song={{ release_id: release.id, track_id: t.id }}
                  title={t.title}
                />
              </div>
            );
          })}
          <details className="album-quality">
            <summary>Album settings</summary>
            <label>
              Preferred quality
              <select
                aria-label="Download preferred quality"
                value={profile}
                onChange={(e) => setProfile(e.target.value)}
              >
                <option value="">Use artist / system preference</option>
                <option value="lossless">FLAC lossless</option>
                <option value="mp3_320">MP3 320 kbps</option>
                <option value="mp3_128">MP3 128 kbps</option>
                <option value="aac_256">AAC 256 kbps</option>
              </select>
            </label>
          </details>
          {editionTotal > 0 && (
            <button
              className="secondary-button edition-switch"
              onClick={() => setChoose(true)}
            >
              Choose another edition · {editionTotal} available
            </button>
          )}
        </>
      ) : !group ? (
        <>
          <ArtistPopular id={artist.id} openAlbum={openGroup} notify={notify} />
          {
            <div className="section-title">
              <h2>Full discography</h2>
              <span>Saved and available releases</span>
            </div>
          }
          <div
            className="tab-list discography-tabs"
            role="tablist"
            aria-label="Release types"
          >
            {[
              ["album", "Albums"],
              ["single", "Singles"],
              ["ep", "EPs"],
              ["other", "Other releases"],
            ].map(([id, label]) => (
              <button
                role="tab"
                aria-selected={kind === id}
                className={kind === id ? "active" : ""}
                key={id}
                onClick={() => {
                  setListing({
                    scope: artist.id + ":" + id,
                    groups: [],
                    total: 0,
                    loading: true,
                  });
                  setVisible(100);
                  setKind(id);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <p className="section-description">
            Newest first · {groups.length}
            {total > groups.length ? ` of ${total}` : ""} releases
            {groupBusy ? " · loading…" : ""}
          </p>
          {groups.slice(0, visible).map((g) => (
            <button
              className="result-row"
              key={scope + ":" + g.id}
              disabled={busy}
              onClick={() => openGroup(g)}
            >
              <Cover
                title={g.title}
                src={catalogueCover("release-group", g.id)}
              />
              <div>
                <strong>{g.title}</strong>
                <span>{[g.date, g.type].filter(Boolean).join(" · ")}</span>
              </div>
              {g.saved_album_id ? (
                <span className="saved-icon discography-saved">
                  <Check size={14} />
                  Saved
                </span>
              ) : (
                <ArrowRight size={16} />
              )}
            </button>
          ))}
          {groups.length < total && (
            <button
              className="secondary-button"
              onClick={() => setVisible((n) => n + 100)}
            >
              More releases
            </button>
          )}
          {!groupBusy && !groups.length && !error && (
            <p className="muted">No releases in this section.</p>
          )}
        </>
      ) : null}
      {!embedded && !group && (
        <ArtistAcquisition id={artist.id} notify={notify} />
      )}
    </section>
  );
}
