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
public struct CatalogueSong: Sendable, Identifiable {
  public let id: String
  public let track: Track
  public let availability: String
  public init(id: String, track: Track, availability: String) {
    self.id = id
    self.track = track
    self.availability = availability
  }
}
public struct CatalogueRelease: Sendable {
  public let id: String
  public let title: String
  public let artist: String
  public let songs: [CatalogueSong]
  public init(id: String, title: String, artist: String, songs: [CatalogueSong]) {
    self.id = id
    self.title = title
    self.artist = artist
    self.songs = songs
  }
}
