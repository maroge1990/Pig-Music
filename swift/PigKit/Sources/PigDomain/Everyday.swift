import Foundation

public struct AccountPreferences: Codable, Sendable {
  public var appearance: String
  public var defaultTab: String
  public init(appearance: String = "system", defaultTab: String = "artists") {
    self.appearance = appearance
    self.defaultTab = defaultTab
  }
}
public struct AccountSession: Codable, Sendable, Identifiable {
  public let id: String
  public let kind: String
  public let deviceName: String
  public let platform: String
  public let lastSeenAt: Double
  public let expiresAt: Double
  public let revokedAt: Double?
}
public struct AccountSessions: Codable, Sendable { public let sessions: [AccountSession] }
public struct PlexStatus: Codable, Sendable {
  public let configured: Bool
  public let label: String?
}
public struct QualityOption: Codable, Sendable, Identifiable {
  public let value: String
  public let label: String
  public var id: String { value }
}
public struct QualityItem: Codable, Sendable {
  public let scope: String
  public let itemId: String
  public let preferred: String
}
public struct QualitySettings: Codable, Sendable {
  public let preferences: [QualityItem]
  public let options: [QualityOption]
  public let householdDefault: String
}
public struct ImportResult: Codable, Sendable {
  public let playlists: Int
  public let tracks: Int
}
public struct RemovalItem: Codable, Sendable, Identifiable {
  public let trackId: String
  public let deleteFile: Bool
  public let keptFor: [String]
  public var id: String { trackId }
}
public struct RemovalPreview: Codable, Sendable {
  public let confirmation: String
  public let items: [RemovalItem]
  public let deleteCount: Int
  public let keepCount: Int
}
public struct RemovalResult: Codable, Sendable {
  public let id: String
  public let removed: Int
  public let deleted: Int
  public let kept: Int
  public let undoUntil: Double
}

public struct ImportPreview: Codable, Sendable {
  public let playlists: Int
  public let tracks: Int
  public let saved: Int
  public let household: Int
  public let missing: Int
}

public struct ArtistAcquisition: Codable, Sendable {
  public let status: String
  public let monitor: Bool
  public let kinds: [String]
  public let total: Int
  public let done: [String]
  public let created: Int
  public let error: String?
}

public struct PlaylistPlexStatus: Codable, Sendable, Hashable {
  public var status: String?
  public var availableCount: Int?
  public var pendingCount: Int?
  public var repeatedCount: Int?
  public var updatedAt: String?
}
public struct CancelledRequest: Codable, Sendable {
  public var cancelled: Bool
  public var continuesForOthers: Bool
}
