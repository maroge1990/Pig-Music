import Foundation
import HTTPTypes
import OpenAPIRuntime
import PigAPI
import PigDomain
import PigStore
import Testing

@testable import PigSync

private actor ConditionalTokens: DeviceTokenStore {
  func read() -> String? { "fixture" }
  func save(_ value: String) {}
  func clear() {}
}
/// Answers like the server: 304 when If-None-Match carries the current ETag.
private actor ConditionalTransport: ClientTransport {
  var name = "Road"
  var sent: [String?] = []
  var bodies = 0
  func rename(_ value: String) { name = value }
  func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws
    -> (HTTPResponse, HTTPBody?)
  {
    // The generated client percent-encodes header values; the server decodes them.
    let validator = request.headerFields[HTTPField.Name("If-None-Match")!]?
      .removingPercentEncoding
    sent.append(validator)
    let etag = "\"\(name)-v1\""
    var response = HTTPResponse(status: .ok)
    response.headerFields[HTTPField.Name("ETag")!] = etag
    if validator == etag {
      response.status = .notModified
      return (response, nil)
    }
    bodies += 1
    response.headerFields[.contentType] = "application/json"
    return (
      response,
      HTTPBody(
        #"{"id":"p1","name":"\#(name)","revision":1,"favourites":false,"track_count":0,"entries":[]}"#
      )
    )
  }
}

struct ConditionalCatalogueTests {
  @Test func aSavedCopyIsRevalidatedAndReusedOn304() async throws {
    let origin = URL(string: "https://fixture.invalid")!
    let transport = ConditionalTransport()
    let service = NativeService(
      server: origin, client: Client(serverURL: origin, transport: transport),
      vault: ConditionalTokens())
    let cache = ConditionalCatalogue(store: try LibraryStore(path: ":memory:"))
    let load: @Sendable (String?) async throws -> Conditional<Playlist> = {
      try await service.playlist(id: "p1", etag: $0)
    }
    let first = try await cache.load(key: "playlist:p1", fetch: load)
    #expect(first.name == "Road")
    let again = try await cache.load(key: "playlist:p1", fetch: load)
    #expect(again.name == "Road")
    #expect(await transport.bodies == 1)
    await transport.rename("Trip")
    let changed = try await cache.load(key: "playlist:p1", fetch: load)
    #expect(changed.name == "Trip")
    #expect(try await cache.load(key: "playlist:p1", fetch: load).name == "Trip")
    #expect(await transport.sent == [nil, "\"Road-v1\"", "\"Road-v1\"", "\"Trip-v1\""])
    #expect(await transport.bodies == 2)
  }
  @Test func a304WithoutASavedCopyAsksAgainWithoutAValidator() async throws {
    let store = try LibraryStore(path: ":memory:")
    let cache = ConditionalCatalogue(store: store)
    let asked = Asked()
    let value = try await cache.load(key: "release:r") { etag -> Conditional<String> in
      let count = await asked.append(etag)
      return count > 1 ? .fresh("body", etag: "\"e\"") : .notModified
    }
    #expect(value == "body")
    #expect(await asked.values == [nil, nil])
    #expect(try await store.cached("catalogue-etag:release:r", as: String.self) == "\"e\"")
  }
}
private actor Asked {
  var values: [String?] = []
  func append(_ value: String?) -> Int {
    values.append(value)
    return values.count
  }
}
