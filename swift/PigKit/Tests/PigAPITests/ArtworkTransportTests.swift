import Foundation
import PigAPI
import PigDomain
import Testing

@testable import PigSync

private actor ArtworkTokens: DeviceTokenStore {
  var token: String? = "disposable-device-token"
  func read() -> String? { token }
  func save(_ token: String) { self.token = token }
  func clear() { token = nil }
}

private final class ArtworkResponses: @unchecked Sendable {
  static let shared = ArtworkResponses()
  private let lock = NSLock()
  private var status = 200
  private var headers = ["Content-Type": "image/png"]
  private var bytes = Data([1, 2, 3])
  private var requests: [URLRequest] = []
  func set(
    status: Int = 200, headers: [String: String] = ["Content-Type": "image/png"],
    bytes: Data = Data([1, 2, 3])
  ) {
    lock.withLock {
      self.status = status
      self.headers = headers
      self.bytes = bytes
      requests = []
    }
  }
  func take(_ request: URLRequest) -> (Int, [String: String], Data) {
    lock.withLock {
      requests.append(request)
      return (status, headers, bytes)
    }
  }
  func captured() -> [URLRequest] { lock.withLock { requests } }
}

private final class ArtworkProtocol: URLProtocol, @unchecked Sendable {
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    let (status, headers, bytes) = ArtworkResponses.shared.take(request)
    client?.urlProtocol(
      self,
      didReceive: HTTPURLResponse(
        url: request.url!, statusCode: status,
        httpVersion: "HTTP/1.1", headerFields: headers)!, cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: bytes)
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}

@Suite(.serialized) struct ArtworkTransportTests {
  private func transport(
    _ tokens: ArtworkTokens = ArtworkTokens(), server: String = "https://fixture.invalid:10000"
  ) -> ArtworkTransport {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [ArtworkProtocol.self]
    return ArtworkTransport(
      server: URL(string: server)!, vault: tokens, configuration: configuration)
  }
  @Test func artworkTransportUsesOnlyValidatedOriginAndDeviceBearer() async throws {
    ArtworkResponses.shared.set()
    let request = try ArtworkRequest(sha: String(repeating: "a", count: 64), width: 128)
    let bytes = try await transport().fetch(request)
    #expect(bytes == Data([1, 2, 3]))
    let sent = try #require(ArtworkResponses.shared.captured().first)
    #expect(sent.url?.host == "fixture.invalid")
    #expect(sent.url?.port == 10000)
    #expect(sent.url?.path == "/api/v1/artwork/" + request.sha)
    #expect(sent.url?.query == "w=128")
    #expect(sent.value(forHTTPHeaderField: "Authorization") == "Bearer disposable-device-token")
    ArtworkResponses.shared.set()
    await #expect(throws: ServerAddress.Invalid.self) {
      try await transport(server: "http://fixture.invalid").fetch(request)
    }
    #expect(ArtworkResponses.shared.captured().isEmpty)
  }
  @Test func artworkTransportRevocationClearsCredentials() async throws {
    ArtworkResponses.shared.set(status: 401, headers: ["Content-Type": "application/json"])
    let tokens = ArtworkTokens()
    let request = try ArtworkRequest(sha: String(repeating: "a", count: 64))
    await #expect(throws: NativeFailure.authentication) {
      try await transport(tokens).fetch(request)
    }
    #expect(await tokens.read() == nil)
    ArtworkResponses.shared.set()
    await #expect(throws: NativeFailure.authentication) {
      try await transport(tokens).fetch(request)
    }
    #expect(ArtworkResponses.shared.captured().isEmpty)
  }
  @Test func artworkTransportRejectsUnexpectedBodiesAndLengths() async throws {
    let request = try ArtworkRequest(sha: String(repeating: "a", count: 64))
    for status in [302, 403, 404, 500] {
      ArtworkResponses.shared.set(
        status: status,
        headers: ["Content-Type": "image/png", "Location": "https://cdn.invalid/art"])
      await #expect(throws: ArtworkFailure.unavailable) { try await transport().fetch(request) }
    }
    ArtworkResponses.shared.set(headers: ["Content-Type": "application/json"])
    await #expect(throws: ArtworkFailure.unavailable) { try await transport().fetch(request) }
    ArtworkResponses.shared.set(headers: ["Content-Type": "image/png", "Content-Length": "2097153"])
    await #expect(throws: ArtworkFailure.tooLarge) { try await transport().fetch(request) }
    ArtworkResponses.shared.set(bytes: Data(repeating: 0, count: 2_097_153))
    await #expect(throws: ArtworkFailure.tooLarge) { try await transport().fetch(request) }
  }
}
