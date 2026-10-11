import Foundation

public struct ArtworkRequest: Hashable, Sendable {
  public let sha: String
  public let width: Int
  public var filename: String { "\(sha)-v1-\(width).image" }
  public init(sha: String, width: Int = 256) throws {
    guard sha.utf8.count == 64,
      sha.utf8.allSatisfy({
        (48...57).contains($0) || (97...102).contains($0)
      }), [128, 256, 512, 1024, 1600].contains(width)
    else {
      throw ArtworkFailure.invalidRequest
    }
    self.sha = sha
    self.width = width
  }
}

public enum ArtworkFailure: Error, Sendable, Equatable {
  case invalidRequest, tooLarge, invalidImage, unavailable
}

public enum CatalogueArtworkKind: String, Sendable {
  case release, releaseGroup = "release-group"
}
