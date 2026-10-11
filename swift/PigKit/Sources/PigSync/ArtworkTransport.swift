import Foundation
import PigAPI
import PigDomain
import PigStore

/// Binary transport until the generated artwork operation declares its image response.
/// Refuse redirects entirely so device credentials cannot follow a CDN/location response.
private final class NoArtworkRedirects: NSObject, URLSessionTaskDelegate, Sendable {
  func urlSession(
    _ session: URLSession, task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
    completionHandler: @escaping @Sendable (URLRequest?) -> Void
  ) { completionHandler(nil) }
}

final class ArtworkTransport: Sendable {
  let server: URL
  let vault: any DeviceTokenStore
  private let session: URLSession
  init(
    server: URL, vault: any DeviceTokenStore, configuration: URLSessionConfiguration = .ephemeral
  ) {
    self.server = server
    self.vault = vault
    configuration.urlCache = nil
    configuration.httpCookieStorage = nil
    configuration.httpShouldSetCookies = false
    configuration.httpMaximumConnectionsPerHost = 4
    configuration.timeoutIntervalForRequest = 20
    configuration.timeoutIntervalForResource = 30
    session = URLSession(
      configuration: configuration, delegate: NoArtworkRedirects(), delegateQueue: nil)
  }
  deinit { session.invalidateAndCancel() }
  func fetch(_ artwork: ArtworkRequest, artist: String? = nil) async throws -> Data {
    let origin = try ServerAddress.validate(server.absoluteString)
    var parts = URLComponents(url: origin, resolvingAgainstBaseURL: false)!
    if let artist {
      guard let uuid = UUID(uuidString: artist) else { throw ArtworkFailure.invalidRequest }
      parts.path = "/api/catalogue/artists/" + uuid.uuidString.lowercased() + "/artwork"
    } else {
      parts.path = "/api/v1/artwork/" + artwork.sha
    }
    parts.queryItems = [URLQueryItem(name: "w", value: String(artwork.width))]
    guard let token = try await vault.read() else { throw NativeFailure.authentication }
    var request = URLRequest(url: parts.url!)
    request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
    request.setValue("image/webp,image/jpeg,image/png", forHTTPHeaderField: "Accept")
    let (bytes, response) = try await session.bytes(for: request)
    defer { bytes.task.cancel() }
    guard let response = response as? HTTPURLResponse else { throw ArtworkFailure.unavailable }
    if response.statusCode == 401 {
      try await vault.clear()
      throw NativeFailure.authentication
    }
    guard response.statusCode == 200, response.url == request.url,
      ["image/webp", "image/jpeg", "image/png"].contains(response.mimeType?.lowercased() ?? "")
    else { throw ArtworkFailure.unavailable }
    guard response.expectedContentLength <= ArtworkCache.maximumImageBytes else {
      throw ArtworkFailure.tooLarge
    }
    var data = Data()
    for try await byte in bytes {
      if data.count >= ArtworkCache.maximumImageBytes { throw ArtworkFailure.tooLarge }
      if data.count % 16384 == 0 { try Task.checkCancellation() }
      data.append(byte)
    }
    return data
  }
}
