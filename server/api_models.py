"""Stable, path-free response shapes shared by web and native clients."""

from typing import Literal
from pydantic import BaseModel, Field

ServerState = Literal[
    "not_in_library", "household_available", "requested", "in_library", "failed"
]


class TrackDTO(BaseModel):
    id: str = ""
    title: str
    artist: str
    album: str = ""
    album_artist: str = ""
    year: str | int = ""
    track_number: int = 0
    disc_number: int = 1
    duration: float = 0
    codec: str | None = None
    bitrate: int | None = None
    album_id: str | None = None
    source_sha: str | None = None
    source_revision: str | None = None
    cover_sha: str | None = None
    cover_url: str | None = None
    available: bool = True
    household_available: bool = False
    musicbrainz_release_id: str | None = None
    musicbrainz_recording_id: str | None = None
    isrcs: list[str] = Field(default_factory=list)
    genre: str | None = None
    server_state: ServerState = "in_library"
    request_progress: float | None = None


class AlbumDTO(BaseModel):
    id: str
    title: str
    artist: str
    artist_id: str = ""
    year: str | int = ""
    category: str = "album"
    track_count: int = 0
    duration: float = 0
    cover_url: str | None = None
    cover_sha: str | None = None
    cover_colour: str | None = None
    musicbrainz_release_id: str | None = None
    edition: str | None = None
    codecs: list[str] = Field(default_factory=list)
    compilation: bool = False
    server_state: ServerState = "in_library"


class ArtistDTO(BaseModel):
    id: str
    name: str
    album_ids: list[str] = Field(default_factory=list)
    album_count: int = 0
    track_count: int = 0
    compilation_only: bool = False
    cover_album_id: str | None = None
    cover_url: str | None = None
    fallback_cover_url: str | None = None
    musicbrainz_artist_id: str | None = None


class AlbumDetail(AlbumDTO):
    tracks: list[TrackDTO]


class ArtistDetail(ArtistDTO):
    albums: list[AlbumDTO]
    compilation_tracks: list[TrackDTO] = Field(default_factory=list)


class TrackPage(BaseModel):
    items: list[TrackDTO]
    total: int
    revision: str
    next_cursor: str | None


class AlbumPage(BaseModel):
    items: list[AlbumDTO]
    total: int
    revision: str
    next_cursor: str | None


class ArtistPage(BaseModel):
    items: list[ArtistDTO]
    total: int
    revision: str
    next_cursor: str | None


class PlaylistEntry(TrackDTO):
    entry_id: str
    position: int
    status: str
    match_kind: str | None = None
    saved_id: str | None = None
    household_available: bool = False
    saved_track: TrackDTO | None = None


class PlaylistDTO(BaseModel):
    id: str
    name: str
    revision: int = 0
    favourites: bool = False
    track_count: int = 0
    available_count: int = 0
    review_count: int = 0
    entries: list[PlaylistEntry] = Field(default_factory=list)


class PlaylistList(BaseModel):
    playlists: list[PlaylistDTO]


class SearchResults(BaseModel):
    tracks: list[TrackDTO]
    household_tracks: list[TrackDTO]
    artists: list[ArtistDTO]


class Entities(BaseModel):
    playlists: list[PlaylistDTO] = Field(default_factory=list)
    tracks: list[TrackDTO] = Field(default_factory=list)
    albums: list[AlbumDTO] = Field(default_factory=list)
    artists: list[ArtistDTO] = Field(default_factory=list)


class DeletedEntities(BaseModel):
    playlists: list[str] = Field(default_factory=list)
    tracks: list[str] = Field(default_factory=list)
    albums: list[str] = Field(default_factory=list)
    artists: list[str] = Field(default_factory=list)


class LibraryChanges(BaseModel):
    revision: str
    upserts: Entities
    deletes: DeletedEntities


class APIError(BaseModel):
    detail: str
    code: str


class UserDTO(BaseModel):
    id: str
    username: str
    display_name: str
    role: Literal["owner", "member"]


class DeviceSessionDTO(BaseModel):
    user: UserDTO
    token: str
    expires_at: int


class PlaybackURL(BaseModel):
    url: str
    expires_in: int


class RequestDTO(BaseModel):
    id: str
    title: str
    artist: str = ""
    album: str = ""
    status: str
    received_bytes: int = 0
    total_bytes: int = 0
    server_state: ServerState
    request_progress: float | None = None
    error: str | None = None


class RequestList(BaseModel):
    total: int
    offset: int
    next_offset: int | None
    library_revision: str
    downloads_enabled: bool
    items: list[RequestDTO]


class RecentAlbums(BaseModel):
    albums: list[AlbumDTO]
    revision: str


class HomeItemDTO(BaseModel):
    id: str
    name: str
    artist: str
    artist_id: str
    kind: Literal["artists", "albums", "songs"]
    release_id: str | None = None
    reason: str | None = None


class HomeFeedDTO(BaseModel):
    artists: list[HomeItemDTO]
    albums: list[HomeItemDTO]
    songs: list[HomeItemDTO]
    source: str
    unavailable: bool
