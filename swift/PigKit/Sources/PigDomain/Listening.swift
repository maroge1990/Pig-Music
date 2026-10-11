import Foundation

/// One qualified listen per queue occurrence. Seeking does not count as listening time.
public struct ListeningEvent: Codable, Sendable, Identifiable {
  public let eventId: String
  public let trackId: String
  public let playedAt: Int
  public let seconds: Int
  public var id: String { eventId }
  public init(eventId: String, trackId: String, playedAt: Int, seconds: Int) {
    self.eventId = eventId
    self.trackId = trackId
    self.playedAt = playedAt
    self.seconds = seconds
  }
}
