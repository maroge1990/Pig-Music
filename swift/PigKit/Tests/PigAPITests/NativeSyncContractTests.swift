import Foundation
import HTTPTypes
import OpenAPIRuntime
import OpenAPIURLSession
import PigAPI
import PigDomain
import PigStore
import XCTest

@testable import PigSync

private actor FixtureTokens: DeviceTokenStore {
  var token: String?
  func read() -> String? { token }
  func save(_ value: String) { token = value }
  func clear() { token = nil }
}
private struct FixtureSession: ClientMiddleware {
  let tokens: FixtureTokens
  func intercept(
    _ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String,
    next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)
  ) async throws -> (HTTPResponse, HTTPBody?) {
    var request = request
    request.headerFields[HTTPField.Name("X-Forwarded-Proto")!] = "https"
    request.headerFields[HTTPField.Name("X-Pig-Request")!] = "1"
    if let token = await tokens.read() { request.headerFields[.authorization] = "Bearer " + token }
    return try await next(request, body, baseURL)
  }
}

final class NativeSyncContractTests: XCTestCase {
  func testPersonalBootstrapSQLiteDeltaAndMediaAgainstServer() async throws {
    guard let address = ProcessInfo.processInfo.environment["PIG_CONTRACT_SERVER"],
      let url = URL(string: address)
    else {
      throw XCTSkip("Set PIG_CONTRACT_SERVER for the isolated native sync journey")
    }
    let tokens = FixtureTokens()
    let client = Client(
      serverURL: url, transport: URLSessionTransport(),
      middlewares: [FixtureSession(tokens: tokens)])
    let service = NativeService(server: url, client: client, vault: tokens)
    let person = try await service.signIn(
      username: "member", password: "browser fixture password", deviceName: "Native sync fixture")
    XCTAssertEqual(person.username, "member")
    let store = try LibraryStore(path: ":memory:")
    let coordinator = SyncCoordinator(source: service, store: store)
    try await coordinator.refresh()
    let tracks = try await store.tracks()
    XCTAssertEqual(tracks.count, 2)
    let albums = try await store.albums()
    XCTAssertEqual(albums.count, 1)
    let albumSongs = try await store.tracks(albumId: albums[0].id)
    XCTAssertEqual(albumSongs.count, 2)
    let revision = try await store.revision()
    XCTAssertNotNil(revision)
    try await coordinator.refresh()
    let following = try await store.revision()
    XCTAssertEqual(revision, following)
    let search = try await store.tracks(query: "Song")
    XCTAssertEqual(search.count, 2)
    let media = try await service.playbackURL(trackId: tracks[0].id)
    XCTAssertEqual(media.host, url.host)
    XCTAssertEqual(media.port, url.port)
    XCTAssertTrue(media.path.contains("playback/files"))
    // The fixture is deliberately HTTP-only. Read its real binary response directly here;
    // production HTTPS/bearer/error handling is covered separately by ArtworkTransportTests.
    let sha = try XCTUnwrap(tracks[0].coverSha)
    var artworkRequest = URLRequest(url: url.appendingPathComponent("api/v1/artwork/" + sha))
    artworkRequest.setValue(
      "Bearer " + (await tokens.read() ?? ""), forHTTPHeaderField: "Authorization")
    artworkRequest.setValue("https", forHTTPHeaderField: "X-Forwarded-Proto")
    let (imageData, imageResponse) = try await URLSession.shared.data(for: artworkRequest)
    XCTAssertEqual((imageResponse as? HTTPURLResponse)?.statusCode, 200)
    XCTAssertEqual(imageResponse.mimeType, "image/webp")
    let image = try ArtworkCache.thumbnail(imageData, width: 256)
    XCTAssertEqual(image.width, 256)
    try await service.signOut()
    let token = await tokens.read()
    XCTAssertNil(token)
  }
}
