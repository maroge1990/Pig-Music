import Foundation
import HTTPTypes
import OpenAPIRuntime
import PigAPI
import PigDomain
import Testing

@testable import PigSync

private actor ActionTokens: DeviceTokenStore {
  func read() -> String? { "fixture" }
  func save(_ value: String) {}
  func clear() {}
}
private actor ActionTransport: ClientTransport {
  let json: String
  let status: Int
  var sent: [(String, Data)] = []
  init(_ json: String, status: Int = 200) {
    self.json = json
    self.status = status
  }
  func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws
    -> (HTTPResponse, HTTPBody?)
  {
    var data = Data()
    if let body { for try await chunk in body { data.append(contentsOf: chunk) } }
    sent.append((request.path ?? "", data))
    var response = HTTPResponse(status: .init(code: status))
    response.headerFields[.contentType] = "application/json"
    return (response, HTTPBody(json))
  }
}
struct PersonalActionTests {
  private func service(_ transport: ActionTransport) -> NativeService {
    let origin = URL(string: "https://fixture.invalid")!
    return NativeService(
      server: origin, client: Client(serverURL: origin, transport: transport), vault: ActionTokens()
    )
  }
  @Test func explicitFavouriteFalseAndRequestPreserveEditionMetadata() async throws {
    var track = Track(
      id: "catalogue", title: "Song", artist: "Artist", album: "Album", duration: 180)
    track.musicbrainzReleaseId = "edition"
    track.musicbrainzRecordingId = "recording"
    track.trackNumber = 2
    track.discNumber = 1
    track.year = .number(2020)
    let transport = ActionTransport(#"{"favourited":false}"#)
    #expect(try await service(transport).favourite(track, value: false) == false)
    let sent = await transport.sent
    #expect(sent.count == 1)
    let body = try #require(JSONSerialization.jsonObject(with: sent[0].1) as? [String: Any])
    #expect(body["favourite"] as? Bool == false)
    let metadata = try #require(body["track"] as? [String: Any])
    #expect(metadata["musicbrainz_release_id"] as? String == "edition")
    #expect(metadata["album_artist"] as? String == "Artist")
    #expect(metadata["year"] as? String == "2020")
    let requests = ActionTransport(
      #"{"created":1,"existing":0,"skipped":0,"downloads_enabled":false}"#)
    let result = try await service(requests).requestMusic([track])
    #expect(result.created == 1 && !result.downloadsEnabled)
    #expect(await requests.sent.count == 1)
  }
  @Test func mutationsDoNotRetryUnconfirmedResponsesOrHideAuthentication() async throws {
    let track = Track(id: "one", title: "Song", artist: "Artist")
    let transport = ActionTransport(#"{"code":"unavailable","detail":"Unavailable"}"#, status: 503)
    do {
      _ = try await service(transport).requestMusic([track])
      Issue.record("Expected unavailable")
    } catch is NativeFailure {}
    #expect(await transport.sent.count == 1)
    let expired = ActionTransport(#"{"code":"unauthorized","detail":"Sign in"}"#, status: 401)
    await #expect(throws: NativeFailure.authentication) {
      try await service(expired).addMembership(trackIds: ["one"])
    }
    #expect(await expired.sent.count == 1)
  }
  @Test func householdReleaseUsesPhysicalFileWithoutClaimingMembership() async throws {
    let transport = ActionTransport(
      #"{"id":"release","title":"Album","artist":"Artist","tracks":[{"id":"catalogue","title":"Song","artist":"Artist","server_state":"household_available","household_track":{"id":"physical","title":"Song","artist":"Artist","server_state":"household_available","source_revision":"v1"}}]}"#
    )
    let release = try await service(transport).catalogueRelease(releaseId: "release")
    #expect(release.songs[0].id == "catalogue")
    #expect(release.songs[0].track.id == "physical")
    #expect(release.songs[0].track.serverState == "household_available")
  }
}
