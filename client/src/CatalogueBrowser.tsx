import { apiFetch } from "./api";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  LoaderCircle,
  ArrowDown,
  Check,
  Play,
  Shuffle,
} from "lucide-react";
import { Cover, catalogueCover } from "./Cover";
import { ArtistPopular } from "./ArtistPopular";
import { MusicLink } from "./MusicLink";
import { mergePage } from "./discography";
import { ArtistAcquisition } from "./ArtistAcquisition";
import { OwnerPanel } from "./OwnerTools";
import { FollowArtist } from "./FollowArtist";
import { ArtistHero } from "./ArtistHero";
import { discoverUrl } from "./navigation";
import type { Discography } from "./discography";
import { SongRow } from "./SongRow";
import { usePlayer } from "./Player";
import { shuffled } from "./shuffle";
import { withLibrary, type Song as Row } from "./songs";

function releaseSongs(release: Release, artistId: string): Row[] {
  const cover = catalogueCover("release", release.id);
  return release.tracks.map((t) => ({
    key: release.id + ":" + t.id,
    title: t.title,
    artist: t.artist,
    album: release.title,
    album_artist: release.artist,
    duration: t.duration,
    track_number: t.track_number,
    disc_number: t.disc_number,
    cover,
    state: pending(t) ? "pending" : "missing",
    release_id: release.id,
    track_id: t.id,
    recording_id: t.musicbrainz_recording_id,
    artist_id: artistId,
  }));
}

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
  musicbrainz_recording_id?: string;
};
type Release = {
  id: string;
  title: string;
  artist: string;
  date: string;
  description: string;
  tracks: Song[];
};
// Request states still in progress on the server.
const pending = (song: { download_status?: string }) =>
  [
    "waiting_for_sources",
    "searching",
    "downloading",
    "validating",
    "importing",
  ].includes(song.download_status || "");
export function CatalogueBrowser({
  artist,
  close,
  notify,
  initialRelease,
  initialGroup,
  owner = false,
}: {
  artist: { id: string; name: string };
  close: () => void;
  notify: (text: string) => void;
  initialRelease?: string;
  initialGroup?: string;
  owner?: boolean;
}) {
  async function request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await apiFetch("/api/v1/catalogue/" + path, options);
    const data = await response.json();
    if (!response.ok)
      throw new Error(
        typeof data.detail === "string" ? data.detail : "Catalogue unavailable",
      );
    return data;
  }
  const [otherReleases, setOtherReleases] = useState(false);
  const [rankedAlbums, setRankedAlbums] = useState<string[]>([]);
  useEffect(() => {
    setRankedAlbums([]);
    void request<{ ranked_album_ids?: string[]; albums: Group[] }>(
      `artists/${artist.id}/popularity`,
    )
      .then((d) =>
        setRankedAlbums(d.ranked_album_ids || d.albums.map((a) => a.id)),
      )
      .catch(() => {});
  }, [artist.id]);
  const [kind, setKind] = useState("album");
  const scope = artist.id + ":" + kind;
  const [listing, setListing] = useState<Discography>({
    scope,
    groups: [],
    total: 0,
    loading: true,
  });
  const [visible, setVisible] = useState(100);
  const allGroups = listing.scope === scope ? listing.groups : [];
  const ranks = new Map(rankedAlbums.map((id, i) => [id, i]));
  const groups =
    kind === "album"
      ? [...allGroups].sort(
          (a, b) =>
            (ranks.get(a.id) ?? Infinity) - (ranks.get(b.id) ?? Infinity) ||
            (a.date || "").localeCompare(b.date || "") ||
            a.title.localeCompare(b.title),
        )
      : allGroups;
  const total = listing.scope === scope ? listing.total : 0;
  const [group, setGroup] = useState<Group | null>(null);
  const [editions, setEditions] = useState<Edition[]>([]);
  const [editionTotal, setEditionTotal] = useState(0);
  const [release, setRelease] = useState<Release | null>(null);
  const [choose, setChoose] = useState(false);
  const player = usePlayer();
  const [rows, setRows] = useState<Row[]>([]);
  useEffect(() => {
    if (!release) return setRows([]);
    const plain = releaseSongs(release, artist.id);
    setRows(plain);
    let active = true;
    void withLibrary(plain)
      .then((found) => active && setRows(found))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [release]);
  const [busy, setBusy] = useState(false);
  const groupBusy = listing.scope !== scope || listing.loading;
  const [error, setError] = useState("");
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
  useEffect(() => {
    if (initialGroup)
      void openGroup({
        id: initialGroup,
        title: "Album",
        date: "",
        type: "Album",
      });
  }, [initialGroup, artist.id]);
  async function loadRelease(id: string) {
    setBusy(true);
    setError("");
    try {
      setRelease(await request<Release>(`releases/${id}`));
      history.replaceState(null, "", "#" + discoverUrl(artist, id));
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
        history.replaceState(
          null,
          "",
          "#" + discoverUrl(artist, data.recommended_id || data.editions[0].id),
        );
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
  async function download() {
    if (!release) return;
    try {
      const response = await apiFetch("/api/v1/requests", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tracks: release.tracks }),
      });
      if (!response.ok) throw new Error("Could not request music");
      notify("Downloading to your library");
      setRows((old) =>
        old.map((r) =>
          r.state === "missing" ? { ...r, state: "pending" } : r,
        ),
      );
      window.dispatchEvent(new Event("music-library-changed"));
      window.dispatchEvent(new Event("music-requests-changed"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function back() {
    setError("");
    if (choose) {
      setChoose(false);
    } else if (group) {
      setGroup(null);
      setRelease(null);
      history.replaceState(null, "", "#" + discoverUrl(artist));
    } else close();
  }
  return (
    <section aria-label="Artist discography">
      {group && (
        <button className="back-button" onClick={back} disabled={busy}>
          <ArrowLeft size={16} />
          {choose ? "Selected edition" : artist.name}
        </button>
      )}
      {!group && (
        <ArtistHero
          back={{ label: "Back", go: back }}
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
      {!group && <FollowArtist id={artist.id} name={artist.name} />}
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
              disabled={!rows.length}
              onClick={() => player.play(rows, 0)}
            >
              <Play size={16} fill="currentColor" /> Play
            </button>
            <button
              className="secondary-button"
              disabled={!rows.length}
              onClick={() => player.play(shuffled(rows), 0)}
            >
              <Shuffle size={16} /> Shuffle
            </button>
            <button
              className="secondary-button"
              disabled={busy || !rows.some((r) => r.state === "missing")}
              onClick={() => download()}
            >
              <ArrowDown size={16} />
              Download album
            </button>
          </div>
          <div className="song-list">
            {rows.map((row, i) => (
              <SongRow
                key={row.key}
                song={row}
                queue={rows}
                index={i}
                numbered
                onAlbum
                onArtist={
                  row.artist.toLocaleLowerCase() ===
                  artist.name.toLocaleLowerCase()
                }
              />
            ))}
          </div>
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
          {!otherReleases && (
            <ArtistPopular id={artist.id} openAlbum={openGroup} songsOnly />
          )}
          {
            <div className="section-title">
              <h2>
                {otherReleases ? "Singles, EPs & other releases" : "All albums"}
              </h2>
              <span>
                {otherReleases
                  ? "Full catalogue"
                  : rankedAlbums.length
                    ? "Popular order"
                    : "Chronological order"}
              </span>
            </div>
          }
          {otherReleases && (
            <div
              className="tab-list discography-tabs"
              role="tablist"
              aria-label="Release types"
            >
              {[
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
          )}
          <p className="section-description">
            {otherReleases
              ? "Newest first"
              : rankedAlbums.length
                ? "Popular first"
                : "Oldest first"}{" "}
            · {groups.length}
            {total > groups.length ? ` of ${total}` : ""} releases
            {groupBusy ? " · loading…" : ""}
          </p>
          <div className={otherReleases ? "release-list" : "full-album-grid"}>
            {groups.slice(0, visible).map((g) => (
              <button
                className={otherReleases ? "result-row" : "album-card"}
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
          </div>
          <button
            className="secondary-button"
            onClick={() => {
              setOtherReleases(!otherReleases);
              setKind(otherReleases ? "album" : "single");
              setVisible(100);
            }}
          >
            {otherReleases
              ? "Back to artist albums"
              : "Singles, EPs & other releases"}
            <ArrowRight size={16} />
          </button>
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
      {owner && !group && (
        <OwnerPanel label="server downloads for this artist">
          <ArtistAcquisition id={artist.id} notify={notify} />
        </OwnerPanel>
      )}
    </section>
  );
}
