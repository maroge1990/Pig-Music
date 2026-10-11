import Foundation

public enum MusicYear: Codable, Sendable, Hashable {
  case text(String)
  case number(Int)
  public var text: String {
    switch self {
    case .text(let value): value
    case .number(let value): String(value)
    }
  }
  public init(from decoder: any Decoder) throws {
    let container = try decoder.singleValueContainer()
    if let number = try? container.decode(Int.self) {
      self = .number(number)
    } else {
      self = .text(try container.decode(String.self))
    }
  }
  public func encode(to encoder: any Encoder) throws {
    var container = encoder.singleValueContainer()
    switch self {
    case .text(let value): try container.encode(value)
    case .number(let value): try container.encode(value)
    }
  }
}
public struct AcquisitionResult: Codable, Sendable {
  public let created: Int
  public let existing: Int
  public let skipped: Int
  public let downloadsEnabled: Bool
}
public struct AcquisitionRequest: Codable, Sendable, Identifiable {
  public let id: String
  public let title: String
  public let artist: String
  public let album: String
  public let status: String
  public let receivedBytes: Int
  public let totalBytes: Int
  public let requestProgress: Double?
  public let error: String?
}
public struct AcquisitionPage: Codable, Sendable {
  public let items: [AcquisitionRequest]
  public let total: Int
  public let active: Int
  public let offset: Int
  public let nextOffset: Int?
  public let downloadsEnabled: Bool
}
