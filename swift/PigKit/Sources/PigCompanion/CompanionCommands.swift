import Foundation
import PigDomain

public struct CompanionEnvelope: Codable, Sendable {
  public var kind: String
  public var context: CompanionContext
  public var file: CompanionFile?
  public init(kind: String, context: CompanionContext, file: CompanionFile? = nil) {
    self.kind = kind
    self.context = context
    self.file = file
  }
}
public struct CompanionCommand: Codable, Sendable {
  public var action: String
  public var account: String?
  public var songIds: [String]
  public var query: String?
  public var listen: ListeningEvent?
  public var offset: Int
  public init(
    _ action: String, account: String?, songIds: [String] = [], query: String? = nil,
    offset: Int = 0, listen: ListeningEvent? = nil
  ) {
    self.action = action
    self.account = account
    self.songIds = songIds
    self.query = query
    self.offset = offset
    self.listen = listen
  }
}
public struct CompanionReply: Codable, Sendable {
  public var songs: [Track]
  public var message: String?
  public var listenId: String?
  public var account: String?
  public init(
    songs: [Track] = [], message: String? = nil, listenId: String? = nil, account: String? = nil
  ) {
    self.songs = songs
    self.message = message
    self.listenId = listenId
    self.account = account
  }
}

/// The Watch's lifecycle log, sent to the phone so one export covers both.
/// The phone sends one without `text` to ask for it.
public struct CompanionDiagnostics: Codable, Sendable {
  public var kind = "diagnostics"
  public var version: String?
  public var text: String?
  public var endedUnexpectedly = false
  public var sentAt: Date
  public init(
    version: String? = nil, text: String? = nil, endedUnexpectedly: Bool = false,
    sentAt: Date = Date()
  ) {
    self.version = version
    self.text = text
    self.endedUnexpectedly = endedUnexpectedly
    self.sentAt = sentAt
  }
  /// Decodes only a diagnostics payload, never another message kind.
  public static func decode(_ data: Data) -> CompanionDiagnostics? {
    guard let value = try? JSONDecoder().decode(Self.self, from: data), value.kind == "diagnostics"
    else { return nil }
    return value
  }
  /// WatchConnectivity user info is limited; the newest entries are sent.
  public static let maximumTextBytes = 48 * 1024
}
