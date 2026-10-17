import Foundation

public enum HomeSection: String, CaseIterable, Sendable {
  case recent, popular, recommended, mixes
}

public struct DiscoveryItem: Codable, Sendable, Identifiable, Hashable {
  public enum Kind: String, Codable, Sendable { case artists, albums, songs }
  public let id: String
  public let name: String
  public let artist: String
  public let artistId: String
  public let kind: Kind
  public let releaseId: String?
  public let album: String
  public let reason: String?

  // Catalogue recording identity must never be used as a saved-library file ID.
  public var playbackTrack: Track? {
    guard kind == .songs else { return nil }
    var track = Track(id: "catalogue:" + id, title: name, artist: artist, album: album)
    track.serverState = "not_in_library"
    track.musicbrainzRecordingId = id
    track.musicbrainzReleaseId = releaseId
    return track
  }
}

public struct DiscoveryFeed: Codable, Sendable {
  public enum State: String, Codable, Sendable {
    case ready
    case noSeeds = "no_seeds"
    case unavailable, preparing
  }
  public let artists: [DiscoveryItem]
  public let albums: [DiscoveryItem]
  public let songs: [DiscoveryItem]
  public let source: String
  public let unavailable: Bool
  public let title: String?
  public let state: State?
}

public struct HomeContent: Codable, Sendable {
  public let albums: [Album]
  public let feed: DiscoveryFeed?
  public let mixes: [PersonalMix]?
  public let mixesPreparing: Bool?
  public let radio: RadioCard?
  public init(
    albums: [Album] = [], feed: DiscoveryFeed? = nil, mixes: [PersonalMix]? = nil,
    mixesPreparing: Bool? = nil, radio: RadioCard? = nil
  ) {
    self.albums = albums
    self.feed = feed
    self.mixes = mixes
    self.mixesPreparing = mixesPreparing
    self.radio = radio
  }
}

/// The person's endless station, shown first among their mixes.
public struct RadioCard: Codable, Sendable, Hashable {
  public let title: String
  public let ready: Int
}

/// The next prepared radio songs; ids are ordinary `mix:` entries.
public struct RadioBatch: Codable, Sendable {
  public let id: String
  public let title: String
  public let tracks: [Track]
  public let preparing: Bool
}

public struct PersonalMix: Codable, Sendable, Identifiable {
  public let id: String
  public let kind: String
  public let day: String
  public let title: String
  public let reason: String
  public let tracks: [Track]
}
