import Foundation

public struct CatalogueGroup: Codable, Sendable, Identifiable {
  public let id: String
  public let title: String
  public let date: String
  public let type: String
}
public struct CatalogueGroups: Codable, Sendable {
  public let total: Int
  public let offset: Int
  public let releases: [CatalogueGroup]
}
public struct CatalogueEdition: Codable, Sendable, Identifiable {
  public let id: String
  public let title: String
  public let date: String
  public let country: String
  public let description: String
  public let status: String
  public let formats: [String]
  public let trackCount: Int
}
public struct CatalogueEditions: Codable, Sendable {
  public let total: Int
  public let offset: Int
  public let editions: [CatalogueEdition]
}
public struct CatalogueSong: Codable, Sendable, Identifiable {
  public let id: String
  public let track: Track
  public let availability: String
  public init(id: String, track: Track, availability: String) {
    self.id = id
    self.track = track
    self.availability = availability
  }
}
public struct CatalogueRelease: Codable, Sendable {
  public let id: String
  public let title: String
  public let artist: String
  /// The first credited artist's catalogue ID; nil for credits without one.
  public let artistId: String?
  public let songs: [CatalogueSong]
  public init(
    id: String, title: String, artist: String, artistId: String? = nil, songs: [CatalogueSong]
  ) {
    self.id = id
    self.title = title
    self.artist = artist
    self.artistId = artistId
    self.songs = songs
  }
}

public struct CataloguePopularSong: Codable, Sendable, Identifiable {
  public var id: String
  public var title: String
  public var artist: String
  public var album: String
  public var releaseId: String
  public var track: Track {
    var song = Track(id: id, title: title, artist: artist, album: album)
    song.musicbrainzRecordingId = id
    song.musicbrainzReleaseId = releaseId
    song.serverState = "not_in_library"
    return song
  }
}
public struct CataloguePopularity: Codable, Sendable {
  public var enabled: Bool
  public var songs: [CataloguePopularSong]
  public var albums: [CatalogueGroup]
  public var rankedAlbumIds: [String]
}
public struct CatalogueProfile: Codable, Sendable {
  public var id: String
  public var name: String
  public var description: String
  public var country: String
  public var type: String
  public var begin: String
  public var end: String
}
public struct ArtistIdentity: Codable, Sendable {
  public var id: String
  public var name: String
}
