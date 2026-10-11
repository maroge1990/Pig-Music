import Foundation

public enum SearchText {
  public static func clean(_ query: String) -> String {
    String(query.trimmingCharacters(in: .whitespacesAndNewlines).prefix(150))
  }
}
public struct LibrarySearchPage: Sendable {
  public let tracks: [Track]
  public let albums: [Album]
  public let artists: [Artist]
  public let offset: Int
  public let nextOffset: Int?
  public let revision: String
  public init(
    tracks: [Track] = [], albums: [Album] = [], artists: [Artist] = [], offset: Int = 0,
    nextOffset: Int? = nil, revision: String = ""
  ) {
    self.tracks = tracks
    self.albums = albums
    self.artists = artists
    self.offset = offset
    self.nextOffset = nextOffset
    self.revision = revision
  }
}
public struct ServerSearchPage: Codable, Sendable {
  public let tracks: [Track]
  public let householdTracks: [Track]
  public let artists: [Artist]
  public let albums: [Album]
  public let offset: Int
  public let nextOffset: Int?
  public let totalHouseholdTracks: Int
  public let revision: String
}
public struct CatalogueArtist: Codable, Sendable, Identifiable {
  public let id: String
  public let name: String
  public let description: String
}
public struct CatalogueArtistPage: Codable, Sendable {
  public let artists: [CatalogueArtist]
  public let total: Int
  public let offset: Int
  public let nextOffset: Int?
}
