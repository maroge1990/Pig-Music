import CryptoKit
import Foundation

public struct Track: Codable, Sendable, Identifiable, Hashable {
  public var id: String
  public var title: String
  public var artist: String
  public var album: String?
  public var albumArtist: String?
  public var year: MusicYear?
  public var albumId: String?
  public var duration: Double?
  public var trackNumber: Int?
  public var discNumber: Int?
  public var codec: String?
  public var coverSha: String?
  public var sourceRevision: String?
  public var serverState: String?
  public var musicbrainzReleaseId: String?
  public var musicbrainzRecordingId: String?
  public init(
    id: String, title: String, artist: String, album: String? = nil, duration: Double? = nil
  ) {
    self.id = id
    self.title = title
    self.artist = artist
    self.album = album
    self.duration = duration
  }
}

public struct Album: Codable, Sendable, Identifiable, Hashable {
  public var id: String
  public var title: String
  public var artist: String
  public var artistId: String?
  public var category: String?
  public var trackCount: Int?
  public var coverSha: String?
  public var year: MusicYear?
  public var duration: Double?
  public var tracks: [Track]?
}

public struct Artist: Codable, Sendable, Identifiable, Hashable {
  public var id: String
  public var name: String
  public var albumIds: [String]?
  public var albumCount: Int?
  public var trackCount: Int?
  public var coverAlbumId: String?
}

public struct PlaylistEntry: Codable, Sendable, Identifiable, Hashable {
  public var entryId: String
  public var id: String { entryId }
  public var title: String
  public var artist: String
  public var album: String?
  public var albumArtist: String?
  public var duration: Double?
  public var trackNumber: Int?
  public var discNumber: Int?
  public var position: Int
  public var year: MusicYear?
  public var serverState: String?
  public var householdAvailable: Bool?
  public var savedId: String?
  public var savedTrack: Track?
  public var musicbrainzReleaseId: String?
  public var musicbrainzRecordingId: String?
}

public struct Playlist: Codable, Sendable, Identifiable, Hashable {
  public var id: String
  public var name: String
  public var revision: Int
  public var favourites: Bool?
  public var trackCount: Int?
  public var plex: PlaylistPlexStatus?
  public var entries: [PlaylistEntry]?
}

public struct Person: Codable, Sendable, Identifiable {
  public var id: String
  public var username: String
  public var displayName: String
  public var role: String
}

public enum LibraryCodec {
  public static func decoder() -> JSONDecoder {
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return decoder
  }
  public static func encoder() -> JSONEncoder {
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    return encoder
  }
  public static func convert<T: Decodable, V: Encodable>(_ value: V, to: T.Type = T.self) throws
    -> T
  {
    try decoder().decode(T.self, from: JSONEncoder().encode(value))
  }
}

public struct LibrarySnapshot: Codable, Sendable {
  public var revision: String
  public var tracks: [Track]
  public var albums: [Album]
  public var artists: [Artist]
  public var playlists: [Playlist]
  public init(
    revision: String, tracks: [Track] = [], albums: [Album] = [], artists: [Artist] = [],
    playlists: [Playlist] = []
  ) {
    self.revision = revision
    self.tracks = tracks
    self.albums = albums
    self.artists = artists
    self.playlists = playlists
  }
}

public struct DeletedEntities: Codable, Sendable {
  public var tracks: [String]
  public var albums: [String]
  public var artists: [String]
  public var playlists: [String]
}

public struct LibraryDelta: Codable, Sendable {
  public var revision: String
  public var upserts: Entities
  public var deletes: DeletedEntities
  public struct Entities: Codable, Sendable {
    public var tracks: [Track]
    public var albums: [Album]
    public var artists: [Artist]
    public var playlists: [Playlist]
  }
}

public enum LibraryCollection: String, CaseIterable, Sendable {
  case tracks, albums, artists, playlists
}

/// Local namespaces never depend on usernames or a server's display name.
public enum LibraryNamespace {
  public static func key(server: URL, personId: String) -> String {
    SHA256.hash(data: Data((server.absoluteString + "\n" + personId).utf8))
      .map { String(format: "%02x", $0) }.joined()
  }
}

extension PlaylistEntry {
  public var playbackTrack: Track {
    if let savedTrack { return savedTrack }
    var track = Track(
      id: savedId ?? entryId, title: title, artist: artist, album: album, duration: duration)
    track.albumArtist = albumArtist
    track.year = year
    track.trackNumber = trackNumber
    track.discNumber = discNumber
    track.musicbrainzReleaseId = musicbrainzReleaseId
    track.musicbrainzRecordingId = musicbrainzRecordingId
    track.serverState =
      householdAvailable == true && savedId != nil ? "household_available" : "not_in_library"
    return track
  }
}

public enum LibrarySort: String, Codable, Sendable, CaseIterable {
  case title, artist, titleDescending
}
