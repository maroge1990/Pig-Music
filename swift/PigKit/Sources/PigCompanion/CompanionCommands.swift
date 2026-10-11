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
