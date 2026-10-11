import Foundation

public struct DeviceCopy: Codable, Sendable {
  public let state: String
  public let quality: String
  public let sha256: String?
  public let sourceSha256: String
  public let bytes: Int64
  public let fileExtension: String
  public let key: String
  enum CodingKeys: String, CodingKey {
    case state, quality, sha256, sourceSha256, bytes, key
    case fileExtension = "extension"
  }
}
public protocol DeviceCopySource: Sendable {
  func deviceCopy(trackId: String, quality: String, create: Bool) async throws -> DeviceCopy
  func copyRequest(trackId: String, quality: String) async throws -> URLRequest
}
public struct DownloadRecord: Codable, Sendable, Identifiable {
  public let track: Track
  public var quality: String
  public var state: String
  public var bytes: Int64
  public var total: Int64
  public var fileName: String?
  public var checksum: String?
  public var error: String?
  public var id: String { track.id }
  public init(track: Track, quality: String) {
    self.track = track
    self.quality = quality
    state = "queued"
    bytes = 0
    total = 0
  }
}
public enum OfflineFailure: Error, LocalizedError, Sendable {
  case authentication, integrity, quota, unsafeResponse, cancelled
  public var errorDescription: String? {
    switch self {
    case .authentication: "The device session expired. Sign in again."
    case .integrity: "The download did not match the server copy. Retry after refreshing."
    case .quota: "The device download budget is full. Remove downloads or increase the budget."
    case .unsafeResponse: "The server did not return a safe audio download."
    case .cancelled: "Download cancelled."
    }
  }
}
