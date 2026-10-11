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
    let recent = try await service.home(.recent)
    XCTAssertEqual(recent.albums.map(\.id), albums.map(\.id))
    XCTAssertEqual(recent.albums.first?.trackCount, 2)
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
    // Verify the signed server/file handoff, including byte-range delivery.
    var mediaRequest = URLRequest(url: media)
    mediaRequest.setValue("bytes=0-63", forHTTPHeaderField: "Range")
    mediaRequest.setValue("https", forHTTPHeaderField: "X-Forwarded-Proto")
    let (mediaBytes, mediaResponse) = try await URLSession.shared.data(for: mediaRequest)
    XCTAssertEqual((mediaResponse as? HTTPURLResponse)?.statusCode, 206)
    XCTAssertEqual(mediaBytes.count, 64)
    XCTAssertEqual(String(data: mediaBytes.prefix(4), encoding: .ascii), "RIFF")
    XCTAssertTrue(
      (mediaResponse as? HTTPURLResponse)?.value(forHTTPHeaderField: "Content-Range")?.hasPrefix(
        "bytes 0-63/") == true)
    let cachedTrack = try await store.track(id: tracks[0].id)
    XCTAssertEqual(cachedTrack?.id, tracks[0].id)
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
    let results = try await service.searchServer(query: "Song")
    XCTAssertEqual(results.tracks.count, 2)
    XCTAssertEqual(results.householdTracks.count, 1)
    let shared = try XCTUnwrap(results.householdTracks.first)
    XCTAssertEqual(shared.serverState, "household_available")
    do {
      _ = try await service.resolve(shared)
      XCTFail("Household playback should require an explicit membership action")
    } catch NativeFailure.unavailable {}
    try await coordinator.refresh()
    let beforeAdd = try await store.count(.tracks)
    XCTAssertEqual(beforeAdd, 2)
    let marked = try await service.favourite(shared, value: true)
    XCTAssertTrue(marked)
    let favourite = try await service.favourite(shared)
    XCTAssertTrue(favourite)
    let unmarked = try await service.favourite(shared, value: false)
    XCTAssertFalse(unmarked)
    try await coordinator.refresh()
    let afterFavourite = try await store.count(.tracks)
    XCTAssertEqual(afterFavourite, 2)
    let added = try await service.addMembership(trackIds: [shared.id])
    XCTAssertEqual(added, 1)
    var savedShared = shared
    savedShared.serverState = "in_library"
    let sharedURL = try await service.resolve(savedShared)
    XCTAssertTrue(sharedURL.path.contains("playback/files"))
    try await coordinator.refresh()
    let afterAdd = try await store.count(.tracks)
    XCTAssertEqual(afterAdd, 3)
    let refreshed = try await service.searchServer(query: "Song")
    XCTAssertEqual(refreshed.householdTracks.count, 0)
    let requested = try await service.requestMusic([
      Track(
        id: "missing", title: "Missing fixture song", artist: "Fixture Artist", album: "Other album"
      )
    ])
    XCTAssertEqual(requested.created, 1)
    let requestPage = try await service.requests()
    XCTAssertEqual(requestPage.items.count, 1)
    XCTAssertEqual(requestPage.items[0].title, "Missing fixture song")
    XCTAssertEqual(requestPage.items[0].status, "waiting_for_sources")
    let cleared = try await service.clearFinishedRequests()
    XCTAssertEqual(cleared, 0)  // Active requests are retained.
    try await service.signOut()
    let token = await tokens.read()
    XCTAssertNil(token)
  }
}
