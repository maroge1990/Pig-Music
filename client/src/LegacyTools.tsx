import { LibraryView } from "./LibraryView";
import { Empty } from "./EmptyState";
import { QueueView, type Queue } from "./QueueView";
import {
  SystemView,
  type Appearance,
  type DownloadSettings,
} from "./SystemView";
import { api, updateArtworkRevision } from "./api";
import { discoverUrl } from "./navigation";
import { useEffect, useRef, useState } from "react";

import {
  ChevronDown,
  Disc3,
  ArrowRight,
  ChevronRight,
  ListMusic,
  FolderHeart,
  Heart,
  LibraryBig,
  LoaderCircle,
  CircleCheck,
  ShieldCheck,
  Search,
  Settings2,
  Upload,
  X,
  Play,
} from "lucide-react";

import type { Album, Artist, Library, Migration, Track } from "./types";

import "./styles.css";

const pigLogo = "/brand/mark.png";
import { CatalogueBrowser } from "./CatalogueBrowser";
import { Cover } from "./Cover";
import { useFixedHeight } from "./useFixedHeight";
import { AlbumCards } from "./LibraryCards";
import { usePlayer } from "./Player";
import { SearchPanel } from "./SearchPanel";

import { RemoveSong } from "./Recovery";

import { SongActions } from "./SongActions";

type Page = "library" | "search" | "migration" | "queue" | "system";

type Route = {
  page: Page;
  artist?: string;
  album?: string;
  catalogue?: string;
  name?: string;
  release?: string;
  playlist?: string;
};

function fromHash(): Route {
  const [path, query] = location.hash.replace(/^#\/?/, "").split("?");
  const [page, kind, id] = path.split("/");
  const parameters = new URLSearchParams(query);

  const safePage: Page = [
    "library",
    "search",
    "migration",
    "queue",
    "system",
  ].includes(page)
    ? (page as Page)
    : "library";

  return {
    page: safePage,
    ...(kind === "artist" && safePage === "search"
      ? {
          catalogue: id,
          name: parameters.get("name") || "Artist",
          release: parameters.get("release") || undefined,
        }
      : kind === "artist"
        ? { artist: id }
        : kind === "album"
          ? { album: id }
          : kind === "playlist"
            ? { playlist: id }
            : {}),
  };
}

const formatTime = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;

const plural = (count: number, noun: string) =>
  `${count.toLocaleString()} ${noun}${count === 1 ? "" : "s"}`;

function PigMark() {
  return <img src={pigLogo} alt="" aria-hidden="true" />;
}

export function LegacyTools() {
  const mobileNav = useFixedHeight("--mobile-nav-height");
  const player = usePlayer();
  const [menuReset, setMenuReset] = useState(0);

  const [route, setRoute] = useState<Route>(fromHash);

  const [library, setLibrary] = useState<Library | null>(null);

  const [importLoaded, setImportLoaded] = useState(false);
  const [migration, setMigration] = useState<Migration | null>(null);

  const [error, setError] = useState("");

  const [toast, setToast] = useState("");

  const [busy, setBusy] = useState(false);

  const [libraryTab, setLibraryTab] = useState("artists");

  const [migrationTab, setMigrationTab] = useState("artists");

  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const [artistDetail, setArtistDetail] = useState<Artist | null>(null);

  const [albumDetail, setAlbumDetail] = useState<Album | null>(null);

  const [detailLoading, setDetailLoading] = useState(false);

  const [reviewOpen, setReviewOpen] = useState(false);

  const [queue, setQueue] = useState<Queue | null>(null);
  const [downloadSettings, setDownloadSettings] =
    useState<DownloadSettings | null>(null);
  const [soulseekHealth, setSoulseekHealth] = useState<{
    configured: boolean;
    connected: boolean;
  } | null>(null);
  useEffect(() => {
    if (route.page !== "system") return;
    const controller = new AbortController();
    void api<{ configured: boolean; connected: boolean }>(
      "/settings/soulseek",
      { signal: controller.signal },
    )
      .then(setSoulseekHealth)
      .catch(() => {});
    return () => controller.abort();
  }, [route.page]);

  const [appearance, setAppearance] = useState<Appearance>(() => {
    try {
      const value = localStorage.getItem("pig-music-appearance");
      return value === "light" || value === "dark" ? value : "system";
    } catch {
      return "system";
    }
  });

  const [sort, setSort] = useState("az");

  const fileInput = useRef<HTMLInputElement>(null);

  const libraryRef = useRef<Library | null>(null);

  const albumCache = useRef(new Map<string, Album>());

  const artistCache = useRef(new Map<string, Artist>());
  const queueSignature = useRef("");

  const main = useRef<HTMLElement>(null);

  const navigate = (page: Page, kind?: "artist" | "album", id?: string) => {
    location.hash = `/${page}${kind && id ? `/${kind}/${id}` : ""}`;
  };

  useEffect(() => {
    const media = matchMedia("(prefers-color-scheme: dark)");

    const apply = () => {
      const theme =
        appearance === "system"
          ? media.matches
            ? "dark"
            : "light"
          : appearance;
      document.documentElement.dataset.theme = theme;
      document
        .querySelector('meta[name="theme-color"]')
        ?.setAttribute("content", theme === "dark" ? "#15111A" : "#FBF8FA");
    };

    apply();
    media.addEventListener("change", apply);

    try {
      localStorage.setItem("pig-music-appearance", appearance);
    } catch {
      /* system still works without storage */
    }

    return () => media.removeEventListener("change", apply);
  }, [appearance]);

  useEffect(() => {
    if (!reviewOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = document.querySelector<HTMLElement>(".review-modal");
    const controls = () =>
      Array.from(
        dialog?.querySelectorAll<HTMLElement>(
          "button:not(:disabled),select:not(:disabled),a[href]",
        ) || [],
      );
    controls()[0]?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setReviewOpen(false);
      if (event.key !== "Tab") return;
      const items = controls();
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [reviewOpen]);

  useEffect(() => {
    const controller = new AbortController();
    let refreshing = false;
    let pending: Queue | undefined;
    const refresh = async (incoming?: Queue) => {
      if (document.hidden) return;
      if (refreshing) {
        pending = incoming;
        return;
      }
      refreshing = true;
      try {
        const q =
          incoming ||
          (await api<Queue>("/queue", { signal: controller.signal }));
        if (controller.signal.aborted) return;
        setQueue(q);
        updateArtworkRevision(q.artwork_revision);
        const signature = `${q.library_revision}:${JSON.stringify(q.media || {})}`;
        if (queueSignature.current && signature !== queueSignature.current) {
          const [l, m] = await Promise.all([
            api<Library>("/library", { signal: controller.signal }),
            api<Migration>("/migration", { signal: controller.signal }),
          ]);
          if (controller.signal.aborted) return;
          queueSignature.current = signature;
          setMigration(m);
          setLibrary(l);
          libraryRef.current = l;
          artistCache.current.clear();
          albumCache.current.clear();
          if (route.artist)
            setArtistDetail(
              await api<Artist>(`/artists/${route.artist}`, {
                signal: controller.signal,
              }),
            );
          if (route.album)
            setAlbumDetail(
              await api<Album>(`/albums/${route.album}`, {
                signal: controller.signal,
              }),
            );
        }
        queueSignature.current = signature;
      } catch (e) {
        if ((e as Error).name !== "AbortError" && route.page === "queue")
          setError((e as Error).message);
      } finally {
        refreshing = false;
        const latest = pending;
        pending = undefined;
        if (latest && !controller.signal.aborted) void refresh(latest);
      }
    };

    let source: EventSource | undefined;
    let connected = false;
    const connect = () => {
      source?.close();
      source = undefined;
      connected = false;
      if (document.hidden || !window.EventSource) return;
      source = new EventSource("/api/events");
      source.onopen = () => {
        connected = true;
        void refresh();
      };
      source.onerror = () => {
        connected = false;
      };
      source.addEventListener("state", (event) => {
        try {
          const state = JSON.parse((event as MessageEvent).data) as {
            queue?: Queue;
            health?: { soulseek?: { configured: boolean; connected: boolean } };
          };
          if (state.queue) void refresh(state.queue);
          if (state.health?.soulseek) setSoulseekHealth(state.health.soulseek);
        } catch {
          connected = false;
        }
      });
    };
    const resume = () => {
      connect();
      if (!document.hidden) void refresh();
    };
    connect();
    void refresh();
    const timer = setInterval(() => {
      if (connected || document.hidden) return;
      void refresh();
      if (route.page === "system")
        void api<{ configured: boolean; connected: boolean }>(
          "/settings/soulseek",
        )
          .then(setSoulseekHealth)
          .catch(() => setSoulseekHealth(null));
    }, 15000);
    document.addEventListener("visibilitychange", resume);
    return () => {
      controller.abort();
      source?.close();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [route.page, route.artist, route.album]);

  useEffect(() => {
    const listener = () => {
      setRoute(fromHash());
      main.current?.scrollTo(0, 0);
      window.scrollTo(0, 0);
    };

    addEventListener("hashchange", listener);

    Promise.all([api<Library>("/library"), api<Migration>("/migration")])
      .then(([l, m]) => {
        libraryRef.current = l;
        setLibrary(l);
        setMigration(m);
      })
      .catch((e) => setError(e.message));
    api<DownloadSettings>("/settings/downloads")
      .then(setDownloadSettings)
      .catch((e) => setError(e.message));

    return () => removeEventListener("hashchange", listener);
  }, []);

  useEffect(() => {
    if (!toast) return;

    const timer = setTimeout(() => setToast(""), 3500);

    return () => clearTimeout(timer);
  }, [toast]);

  useEffect(() => {
    let current = true;

    setArtistDetail(null);
    setAlbumDetail(null);

    const id = route.artist || route.album;

    if (!id) {
      setDetailLoading(false);
      return;
    }

    setDetailLoading(true);

    if (route.artist) {
      const cached = artistCache.current.get(id);

      (cached ? Promise.resolve(cached) : api<Artist>(`/artists/${id}`))
        .then((a) => {
          artistCache.current.set(id, a);
          if (current) setArtistDetail(a);
        })
        .catch((e) => {
          if (current) setError(e.message);
        })
        .finally(() => {
          if (current) setDetailLoading(false);
        });
    } else {
      const cached = albumCache.current.get(id);

      (cached ? Promise.resolve(cached) : api<Album>(`/albums/${id}`))
        .then((a) => {
          albumCache.current.set(id, a);
          if (current) setAlbumDetail(a);
        })
        .catch((e) => {
          if (current) setError(e.message);
        })
        .finally(() => {
          if (current) setDetailLoading(false);
        });
    }

    return () => {
      current = false;
    };
  }, [route.artist, route.album]);

  const selectTracks = async (ids: string[], selected: boolean) => {
    if (busy || !ids.length) return;

    setBusy(true);

    try {
      setMigration(
        await api<Migration>("/migration/selection", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ track_ids: ids, selected }),
        }),
      );

      return true;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const decideTrack = async (track_id: string, decision: string) => {
    setBusy(true);

    try {
      setMigration(
        await api<Migration>("/migration/decision", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ track_id, decision }),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const submitImport = async () => {
    setBusy(true);

    try {
      const result = await api<{
        created: number;
        existing: number;
        skipped: number;
      }>("/migration/submit", { method: "POST" });

      setReviewOpen(false);
      setToast(
        `${result.created} added to queue · ${result.existing} already queued · ${result.skipped} skipped`,
      );
      navigate("queue");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const importAll = async () => {
    if (!migration || busy) return;

    const ids = migration.albums.flatMap((a) =>
      (a.tracks || [])
        .filter((t) => t.status !== "downloaded")
        .map((t) => t.id),
    );

    if (await selectTracks(ids, true)) {
      if (
        migration.albums.some((a) =>
          (a.tracks || []).some((t) => t.status === "review" && !t.decision),
        )
      )
        setReviewOpen(true);
      else await submitImport();
    }
  };

  const importFile = async (file?: File) => {
    if (!file) return;

    if (
      migration?.stats.selected &&
      !window.confirm(
        "Importing a new inventory will clear the current selections. Continue?",
      )
    )
      return;

    setBusy(true);

    try {
      setMigration(
        await api<Migration>("/migration/import", {
          method: "POST",
          headers: { "Content-Type": "application/xml" },
          body: file,
        }),
      );

      setLibrary(await api<Library>("/library"));
      setExpanded(new Set());
      setToast("Inventory imported. Choose the music you want to keep.");

      setImportLoaded(true);
      navigate("migration");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  useEffect(() => {
    const refresh = () => {
      artistCache.current.clear();
      albumCache.current.clear();
      void api<Library>("/library")
        .then((value) => {
          setLibrary(value);
          libraryRef.current = value;
          if (
            (route.album && !value.albums.some((a) => a.id === route.album)) ||
            (route.artist && !value.artists.some((a) => a.id === route.artist))
          ) {
            navigate("library");
            return;
          }
          if (route.album)
            void api<Album>("/albums/" + route.album)
              .then(setAlbumDetail)
              .catch((e) => setError(e.message));
          if (route.artist)
            void api<Artist>("/artists/" + route.artist)
              .then(setArtistDetail)
              .catch((e) => setError(e.message));
        })
        .catch((e) => setError(e.message));
    };
    window.addEventListener("music-library-changed", refresh);
    return () => window.removeEventListener("music-library-changed", refresh);
  }, [route]);
  const toggleExpanded = (id: string) =>
    setExpanded((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const navItems = [
    {
      page: "library" as Page,
      label: "Your library",
      short: "Library",
      icon: LibraryBig,
    },

    {
      page: "search" as Page,
      label: "Search & discover",
      short: "Search",
      icon: Search,
    },

    {
      page: "migration" as Page,
      label: "Import library",
      short: "Import",
      icon: FolderHeart,
    },

    {
      page: "queue" as Page,
      label: "Download queue",
      short: "Queue",
      icon: ListMusic,
    },
  ];

  const openAlbum = (id: string) => navigate("library", "album", id);

  const openArtist = (id: string) => navigate("library", "artist", id);

  const albumCards = (albums: Album[]) => (
    <AlbumCards albums={albums} open={openAlbum} />
  );

  const savedTracks = (tracks: Track[]) => (
    <div className="track-list">
      {tracks.map((track) => (
        <div className="track-row" key={track.id}>
          <button
            className="track-position track-play"
            aria-label={`Play ${track.title}`}
            disabled={track.available === false}
            onClick={() =>
              player.playSaved(
                track,
                tracks.filter((t) => t.available !== false),
              )
            }
          >
            <Play size={15} />
          </button>
          <div className="track-name">
            <strong>{track.title}</strong>
            <span>{track.artist}</span>
          </div>

          <SongActions song={{ saved_id: track.id }} title={track.title} />
          <RemoveSong id={track.id} title={track.title} />
          <span className="track-quality">
            {track.codec?.toUpperCase()}
            {track.bitrate ? ` · ${track.bitrate}k` : ""}
          </span>
          <span className="track-time">{formatTime(track.duration)}</span>
          {track.available === false ? (
            <span className="track-quality">File unavailable</span>
          ) : (
            <CircleCheck size={17} className="saved-icon" />
          )}
        </div>
      ))}
    </div>
  );

  async function changeCategory(category: string) {
    if (!albumDetail) return;

    setBusy(true);
    try {
      const updated = await api<Library>(`/albums/${albumDetail.id}/category`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: category }),
      });
      setLibrary(updated);
      libraryRef.current = updated;
      albumCache.current.clear();
      artistCache.current.clear();
      setAlbumDetail(await api<Album>(`/albums/${albumDetail.id}`));
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function reviewPlaylist(id: string) {
    try {
      setMigration(
        await api<Migration>("/playlists/" + id + "/review", {
          method: "POST",
        }),
      );
      setImportLoaded(true);
      navigate("migration");
    } catch (e) {
      setToast((e as Error).message);
    }
  }
  function discoverArtist(artist: {
    id: string;
    name: string;
    description?: string;
  }) {
    location.hash = discoverUrl(artist);
  }
  function resetMenu(page: Page) {
    setMenuReset((n) => n + 1);
    if (page === "library") setLibraryTab("artists");
    navigate(page);
    main.current?.scrollTo(0, 0);
    window.scrollTo(0, 0);
  }
  function searchPage() {
    if (route.catalogue)
      return (
        <CatalogueBrowser
          key={route.catalogue}
          artist={{ id: route.catalogue, name: route.name || "Artist" }}
          initialRelease={route.release}
          close={() => navigate("search")}
          notify={setToast}
        />
      );
    return (
      <>
        <div className="section-title">
          <h1>Search &amp; discover</h1>
        </div>
        <SearchPanel
          key={menuReset}
          onArtist={openArtist}
          onAlbum={openAlbum}
          onDiscover={discoverArtist}
          onMigration={() => navigate("migration")}
        />
      </>
    );
  }

  function migrationPage() {
    if (!migration || !importLoaded)
      return (
        <>
          <div className="page-heading">
            <h1>Import library</h1>
          </div>
          <Empty
            title="Import an Apple Music export"
            description="Upload an XML export to import playlists and select music to add to your library."
          />
          <button
            className="primary-button"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
          >
            <Upload size={16} />
            Import XML
          </button>
        </>
      );

    const visible = migration.albums.filter((a) =>
      migrationTab === "compilations" ? a.compilation : !a.compilation,
    );

    const groups = new Map<string, Album[]>();

    for (const album of visible) {
      const group = migrationTab === "compilations" ? album.id : album.artist;
      groups.set(group, [...(groups.get(group) || []), album]);
    }

    return (
      <>
        <div className="page-heading migration-heading">
          <div>
            <h1>Import library</h1>
          </div>
          <button
            className="secondary-button"
            disabled={busy}
            onClick={() => fileInput.current?.click()}
          >
            <Upload size={16} /> Import XML
          </button>
        </div>

        <div className="migration-summary">
          <div className="inventory-name">
            <span className="inventory-icon">
              <Heart size={20} />
            </span>
            <div>
              <strong>{migration.source_name}</strong>
              <span>
                Apple Music inventory ·{" "}
                {plural(migration.stats.tracks, "track")}
              </span>
            </div>
          </div>
          <div className="inventory-counts">
            <span>
              <i className="green-dot" />
              {migration.stats.saved} already saved
            </span>
            <span>
              <i className="peach-dot" />
              {migration.stats.missing} missing
            </span>
            {migration.stats.review > 0 && (
              <span>
                <i className="amber-dot" />
                {migration.stats.review} to check
              </span>
            )}
          </div>
        </div>

        <div className="review-note">
          <ShieldCheck size={19} />
          <p>
            Import every song in this export, or choose a smaller selection.
            Already saved music is skipped. Requests use your download settings
            and save into your SMB library.
          </p>
        </div>

        <div className="import-actions">
          <button
            className="primary-button"
            disabled={
              busy || (!migration.stats.missing && !migration.stats.review)
            }
            onClick={importAll}
          >
            Import all <ArrowRight size={16} />
          </button>
          <button
            className="secondary-button"
            disabled={busy || !migration.stats.selected}
            onClick={() =>
              selectTracks(
                migration.albums.flatMap((a) =>
                  (a.tracks || []).filter((t) => t.selected).map((t) => t.id),
                ),
                false,
              )
            }
          >
            Clear selection
          </button>
        </div>
        <div className="library-controls">
          <div
            className="tab-list"
            role="tablist"
            aria-label="Migration groups"
          >
            <button
              role="tab"
              aria-selected={migrationTab === "artists"}
              className={migrationTab === "artists" ? "active" : ""}
              onClick={() => setMigrationTab("artists")}
            >
              Artists & albums
            </button>
            <button
              role="tab"
              aria-selected={migrationTab === "compilations"}
              className={migrationTab === "compilations" ? "active" : ""}
              onClick={() => setMigrationTab("compilations")}
            >
              Compilations
              <span>
                {migration.albums.filter((a) => a.compilation).length}
              </span>
            </button>
          </div>
          <span className="muted small">
            {plural(
              groups.size,
              migrationTab === "compilations" ? "compilation" : "artist",
            )}
          </span>
        </div>

        <div className="migration-groups">
          {[...groups].map(([id, albums]) => {
            const tracks = albums.flatMap((a) => a.tracks || []);
            const saved = tracks.filter(
              (t) => t.status === "downloaded",
            ).length;

            const selected = tracks.filter((t) => t.selected).length;
            const missing = tracks.filter((t) => t.status === "missing");

            const allMissingSelected =
              missing.length > 0 && missing.every((t) => t.selected);

            return (
              <section
                className={`migration-group ${expanded.has(id) ? "expanded" : ""}`}
                key={id}
              >
                <div className="group-head">
                  <button
                    className="group-expand"
                    aria-expanded={expanded.has(id)}
                    onClick={() => toggleExpanded(id)}
                  >
                    <Cover
                      title={
                        migrationTab === "compilations" ? albums[0].title : id
                      }
                      src={albums[0].cover_url}
                      artist={migrationTab !== "compilations"}
                    />
                    <div>
                      <strong>
                        {migrationTab === "compilations" ? albums[0].title : id}
                      </strong>
                      <span>
                        {plural(albums.length, "release")} ·{" "}
                        {plural(tracks.length, "track")}
                        {saved > 0 && ` · ${saved} saved`}
                      </span>
                    </div>
                    <ChevronDown size={17} />
                  </button>

                  <div className="group-actions">
                    {selected > 0 && (
                      <span className="selection-count">
                        {selected} selected
                      </span>
                    )}
                    <button
                      className={`small-button ${allMissingSelected ? "selected-button" : ""}`}
                      disabled={busy || saved === tracks.length}
                      onClick={() =>
                        missing.length
                          ? selectTracks(
                              missing.map((t) => t.id),
                              !allMissingSelected,
                            )
                          : toggleExpanded(id)
                      }
                    >
                      <Heart size={13} />{" "}
                      {allMissingSelected
                        ? "Selected"
                        : missing.length
                          ? "Select missing"
                          : saved === tracks.length
                            ? "Already saved"
                            : "Check versions"}
                    </button>
                  </div>
                </div>

                {expanded.has(id) && (
                  <div className="group-content">
                    {albums.map((album) => {
                      const eligible = (album.tracks || []).filter(
                        (t) => t.status === "missing",
                      );

                      const allSelected =
                        !!eligible.length && eligible.every((t) => t.selected);

                      return (
                        <div className="migration-album" key={album.id}>
                          <div className="migration-album-head">
                            <Disc3 size={16} />
                            <div>
                              <strong>{album.title}</strong>
                              <span>
                                {album.year || "Release"} ·{" "}
                                {plural(album.track_count, "track")}
                              </span>
                            </div>
                            <button
                              className="text-button"
                              disabled={busy || !eligible.length}
                              onClick={() =>
                                selectTracks(
                                  eligible.map((t) => t.id),
                                  !allSelected,
                                )
                              }
                            >
                              {allSelected
                                ? "Deselect missing"
                                : eligible.length
                                  ? "Select missing"
                                  : album.saved_count === album.track_count
                                    ? "Already saved"
                                    : "Check versions"}
                            </button>
                          </div>

                          {(album.tracks || []).map((track) => (
                            <label
                              className={`migration-track ${track.selected ? "chosen" : ""}`}
                              key={track.id}
                            >
                              <input
                                type="checkbox"
                                aria-label={`Keep ${track.title} by ${track.artist}`}
                                checked={!!track.selected}
                                disabled={busy || track.status === "downloaded"}
                                onChange={(e) =>
                                  selectTracks([track.id], e.target.checked)
                                }
                              />
                              <span className="track-position">
                                {track.track_number || "–"}
                              </span>
                              <div className="track-name">
                                <strong>{track.title}</strong>
                                <span>{track.artist}</span>
                                {track.status === "review" && (
                                  <small>{track.reason}</small>
                                )}
                              </div>
                              <span className="track-time">
                                {formatTime(track.duration)}
                              </span>
                              <span
                                className={`migration-status ${track.status}`}
                              >
                                {track.status === "downloaded" ? (
                                  <>
                                    <CircleCheck size={13} />
                                    Saved
                                  </>
                                ) : track.status === "review" ? (
                                  "Check version"
                                ) : (
                                  "Missing"
                                )}
                              </span>
                            </label>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>
            );
          })}
        </div>

        {!groups.size && (
          <Empty
            title={
              migration.stats.tracks
                ? "No compilations in this inventory"
                : "Start with an export"
            }
            description={
              migration.stats.tracks
                ? "Multi-artist releases will appear here when they are in your export."
                : "Import an Apple Music XML export to review what you want to retain."
            }
          />
        )}

        <div className="migration-footer">
          <div>
            <span className="footer-icon">
              <Heart size={18} />
            </span>
            <div>
              <strong>
                {migration.stats.selected
                  ? plural(migration.stats.selected, "track") + " selected"
                  : "No songs selected"}
              </strong>
              <span>
                {migration.stats.selected
                  ? "Ready to submit to the download queue"
                  : "Select songs to import."}
              </span>
            </div>
          </div>
          <button
            className="primary-button"
            disabled={busy || !migration.stats.selected}
            onClick={() =>
              unresolved.length ? setReviewOpen(true) : submitImport()
            }
          >
            Import now <ArrowRight size={16} />
          </button>
        </div>
      </>
    );
  }

  const queueAction = async (id: string, action: string) => {
    setBusy(true);
    try {
      setQueue(await api<Queue>(`/queue/${id}/${action}`, { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const saveDownloads = async () => {
    if (!downloadSettings) return;
    setBusy(true);
    try {
      setDownloadSettings(
        await api<DownloadSettings>("/settings/downloads", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(downloadSettings),
        }),
      );
      setToast("Download settings saved");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  async function clearQueue() {
    if (!queue?.items.length) return;
    const unfinished = queue.items.some(
      (t) => !["completed", "cancelled", "failed"].includes(t.status),
    );
    if (
      unfinished &&
      !window.confirm(
        "Cancel unfinished downloads and clear the queue? Downloaded music will be kept.",
      )
    )
      return;
    setBusy(true);
    try {
      setQueue(await api<Queue>("/queue/clear", { method: "POST" }));
      setToast("Queue cleared. Downloaded music kept.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (route.playlist) setLibraryTab("playlists");
  }, [route.playlist]);
  const selectedTracks =
    migration?.albums.flatMap((a) =>
      (a.tracks || []).filter((t) => t.selected),
    ) || [];

  const conflicts = selectedTracks.filter((t) => t.status === "review");

  const unresolved = conflicts.filter((t) => !t.decision);

  return (
    <div className="app-shell">
      <input
        type="file"
        ref={fileInput}
        className="sr-only"
        accept=".xml,application/xml,text/xml"
        onChange={(e) => importFile(e.target.files?.[0])}
      />
      <aside className="sidebar">
        <button
          className="brand"
          aria-label="PigMusic · Your library"
          onClick={() => navigate("library")}
        >
          <img
            className="brand-lockup brand-dark"
            src="/brand/lockup-horizontal-dark.svg"
            alt=""
          />
          <img
            className="brand-lockup brand-light"
            src="/brand/lockup-horizontal-light.svg"
            alt=""
          />
        </button>
        <div className="sidebar-section-label">COLLECTION</div>
        <nav aria-label="Main navigation">
          {navItems.map((item) => (
            <button
              className={`nav-item ${route.page === item.page ? "active" : ""}`}
              key={item.page}
              onClick={() => resetMenu(item.page)}
            >
              <item.icon size={19} />
              <span>{item.label}</span>
              {item.page === "queue" &&
                !!queue?.items.filter(
                  (t) => !["completed", "cancelled"].includes(t.status),
                ).length && (
                  <span className="nav-count">
                    {
                      queue.items.filter(
                        (t) => !["completed", "cancelled"].includes(t.status),
                      ).length
                    }
                  </span>
                )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="connection-card">
            <span className="connection-dot" />
            <div>
              <strong>Music library</strong>
              <small>
                {library
                  ? `${library.stats.tracks.toLocaleString()} tracks · snapshot ready`
                  : "Connecting…"}
              </small>
            </div>
          </div>
          <button
            className={`nav-item ${route.page === "system" ? "active" : ""}`}
            onClick={() => navigate("system")}
          >
            <Settings2 size={18} />
            <span>System & settings</span>
          </button>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <span className="breadcrumb-brand">
              <span className="mobile-brand-mark">
                <PigMark />
              </span>
              Pig Music
            </span>
            <ChevronRight size={13} />
            <strong>
              {route.page === "library"
                ? "Your library"
                : route.page === "search"
                  ? "Discover"
                  : route.page === "migration"
                    ? "Import"
                    : route.page === "queue"
                      ? "Queue"
                      : "System"}
            </strong>
          </div>
          <SearchPanel
            compact
            key={menuReset}
            onArtist={openArtist}
            onAlbum={openAlbum}
            onDiscover={discoverArtist}
            onMigration={() => navigate("migration")}
          />
          <button
            className="mobile-system icon-button"
            aria-label="System and settings"
            onClick={() => navigate("system")}
          >
            <Settings2 size={20} />
          </button>
        </header>

        <main
          ref={main}
          className={`main-content ${route.page === "migration" ? "migration-page" : ""}`}
        >
          {error && (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}

          {!library && !error && (
            <div className="loading-block">
              <LoaderCircle className="spin" />
              Opening your collection…
            </div>
          )}

          {library &&
            (route.page === "library" ? (
              <LibraryView
                library={library}
                detailLoading={detailLoading}
                albumDetail={albumDetail}
                artistDetail={artistDetail}
                navigate={navigate}
                openArtist={openArtist}
                openAlbum={openAlbum}
                player={player}
                albumCards={albumCards}
                savedTracks={savedTracks}
                libraryTab={libraryTab}
                setLibraryTab={setLibraryTab}
                sort={sort}
                setSort={setSort}
                setToast={setToast}
                playlist={route.playlist}
                busy={busy}
                changeCategory={changeCategory}
                reviewPlaylist={reviewPlaylist}
                prefetchArtist={(id) => {
                  if (!artistCache.current.has(id))
                    api<Artist>(`/artists/${id}`)
                      .then((a) => artistCache.current.set(a.id, a))
                      .catch(() => {});
                }}
              />
            ) : route.page === "search" ? (
              searchPage()
            ) : route.page === "migration" ? (
              migrationPage()
            ) : route.page === "queue" ? (
              <QueueView
                queue={queue}
                busy={busy}
                clearQueue={clearQueue}
                queueAction={queueAction}
              />
            ) : (
              <SystemView
                appearance={appearance}
                setAppearance={setAppearance}
                library={library}
                downloadSettings={downloadSettings}
                setDownloadSettings={setDownloadSettings}
                soulseekHealth={soulseekHealth}
                busy={busy}
                saveDownloads={saveDownloads}
                setToast={setToast}
                refresh={() => {
                  artistCache.current.clear();
                  albumCache.current.clear();
                  void api<Library>("/library").then(setLibrary);
                }}
              />
            ))}
        </main>
      </div>
      <nav
        ref={mobileNav}
        className="mobile-nav"
        aria-label="Mobile navigation"
      >
        {navItems.map((item) => (
          <button
            className={route.page === item.page ? "active" : ""}
            key={item.page}
            onClick={() => resetMenu(item.page)}
          >
            <span className="mobile-nav-icon">
              <item.icon size={21} />
              {item.page === "queue" &&
                !!queue?.items.filter(
                  (t) => !["completed", "cancelled"].includes(t.status),
                ).length && (
                  <span className="mobile-queue-count">
                    {
                      queue.items.filter(
                        (t) => !["completed", "cancelled"].includes(t.status),
                      ).length
                    }
                  </span>
                )}
            </span>
            <span>{item.short}</span>
          </button>
        ))}
      </nav>

      {toast && (
        <div className="toast" role="status">
          <CircleCheck size={17} />
          {toast}
        </div>
      )}

      {reviewOpen && (
        <div
          className="modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) setReviewOpen(false);
          }}
        >
          <section
            className="review-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-title"
          >
            <div className="modal-heading">
              <div>
                <div className="eyebrow">ONLY THE UNCERTAIN ONES</div>
                <h2 id="review-title">Check these versions.</h2>
              </div>
              <button
                className="icon-button"
                aria-label="Close review"
                onClick={() => setReviewOpen(false)}
              >
                <X size={20} />
              </button>
            </div>
            <p>
              {plural(unresolved.length, "decision")} remaining. Other selected
              songs are ready. Keep the recording and release requested in your
              export, or skip this song.
            </p>
            <div className="review-tracks">
              {conflicts.map((t) => (
                <div className="conflict-row" key={t.id}>
                  <div>
                    <strong>{t.title}</strong>
                    <span>
                      {t.artist} · {t.album}
                    </span>
                    <span>{t.reason}</span>
                    <label>
                      Version choice
                      <select
                        aria-label={`Version choice for ${t.title} by ${t.artist}`}
                        disabled={busy}
                        value={t.decision || ""}
                        onChange={(e) => decideTrack(t.id, e.target.value)}
                      >
                        <option value="" disabled>
                          Choose…
                        </option>
                        <option value="requested">
                          Keep requested release
                        </option>
                        <option value="skip">Skip this song</option>
                      </select>
                    </label>
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button
                className="secondary-button"
                onClick={() => setReviewOpen(false)}
              >
                Back to selection
              </button>
              <button
                className="primary-button"
                disabled={busy || unresolved.length > 0}
                onClick={submitImport}
              >
                Import now <ArrowRight size={16} />
              </button>
            </div>
            <p>
              Requests are saved in the queue and downloaded when enabled in
              System settings.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}
