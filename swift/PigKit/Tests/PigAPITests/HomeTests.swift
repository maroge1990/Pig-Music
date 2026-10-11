import Foundation
import HTTPTypes
import OpenAPIRuntime
import PigAPI
import PigDomain
import Testing

@testable import PigSync

private actor HomeTokens: DeviceTokenStore {
  func read() -> String? { "fixture" }
  func save(_ value: String) {}
  func clear() {}
}
private actor HomeTransport: ClientTransport {
  let status: Int
  let json: String
  var paths: [String] = []
  init(status: Int = 200, json: String) {
    self.status = status
    self.json = json
  }
  func send(_ request: HTTPRequest, body: HTTPBody?, baseURL: URL, operationID: String) async throws
    -> (HTTPResponse, HTTPBody?)
  {
    paths.append(request.path ?? "")
    var response = HTTPResponse(status: .init(code: status))
    response.headerFields[.contentType] = "application/json"
    return (response, HTTPBody(json))
  }
}

struct HomeTests {
  private func service(_ transport: HomeTransport) -> NativeService {
    let origin = URL(string: "https://fixture.invalid")!
    return NativeService(
      server: origin, client: Client(serverURL: origin, transport: transport), vault: HomeTokens())
  }
  @Test func discoveryKeepsRecordingAndReleaseIdentitySeparateFromSavedFiles() async throws {
    let transport = HomeTransport(
      json:
        #"{"artists":[],"albums":[],"songs":[{"id":"recording-one","name":"First Light","artist":"The Orchard","artist_id":"artist-one","kind":"songs","release_id":"release-one","album":"Sunrise","reason":"Similar to Riverlight"}],"source":"Similar to artists in your library","unavailable":false,"state":"ready"}"#
    )
    let result = try await service(transport).home(.recommended)
    let item = try #require(result.feed?.songs.first)
    let track = try #require(item.playbackTrack)
    #expect(track.id == "catalogue:recording-one")
    #expect(track.serverState == "not_in_library")
    #expect(track.musicbrainzRecordingId == "recording-one")
    #expect(track.musicbrainzReleaseId == "release-one")
    #expect(item.reason == "Similar to Riverlight")
    #expect(await transport.paths == ["/api/v1/home/recommended"])
  }
  @Test func recentUsesPersonalAlbumIDsAndCovers() async throws {
    let transport = HomeTransport(
      json:
        #"{"albums":[{"id":"saved-album","title":"Sunrise","artist":"The Orchard","artist_id":"saved-artist","category":"albums","track_count":2,"cover_sha":"abc","date":"","year":"","musicbrainz_release_id":null,"edition":null,"codecs":[],"compilation":false,"server_state":"in_library"}],"revision":"v1"}"#
    )
    let content = try await service(transport).home(.recent)
    #expect(content.albums.first?.id == "saved-album")
    #expect(content.albums.first?.coverSha == "abc")
    #expect(content.feed == nil)
    #expect(await transport.paths == ["/api/v1/home/recent"])
  }
  @Test func discoveryProviderStatesRemainDistinct() async throws {
    for state in ["preparing", "no_seeds", "unavailable", "ready"] {
      let transport = HomeTransport(
        json:
          "{\"artists\":[],\"albums\":[],\"songs\":[],\"source\":\"Chart\",\"unavailable\":\(state == "unavailable"),\"state\":\"\(state)\"}"
      )
      let result = try await service(transport).home(.popular)
      #expect(result.feed?.state?.rawValue == state)
      #expect(await transport.paths == ["/api/v1/home/popular"])
    }
  }
  @Test func expiredSessionIsNotReportedAsProviderOutage() async throws {
    for section in HomeSection.allCases {
      let transport = HomeTransport(
        status: 401, json: #"{"code":"unauthorized","detail":"Sign in"}"#)
      await #expect(throws: NativeFailure.authentication) {
        try await service(transport).home(section)
      }
    }
  }
}

struct CatalogueContractTests {
  private func service(_ json: String) -> NativeService {
    let origin = URL(string: "https://fixture.invalid")!
    return NativeService(
      server: origin, client: Client(serverURL: origin, transport: HomeTransport(json: json)),
      vault: HomeTokens())
  }
  @Test func releaseUsesPersonalFileIDButPreservesCataloguePositionsAndAvailability() async throws {
    let json =
      #"{"id":"release","title":"Album","artist":"Artist","tracks":[{"id":"catalogue-track","title":"Song","artist":"Artist","track_number":2,"disc_number":1,"server_state":"in_library","saved_track":{"id":"file-id","title":"Song","artist":"Artist","source_revision":"v7","server_state":"in_library"}},{"id":"requested","title":"Another","artist":"Artist","server_state":"requested","saved_track":null}]}"#
    let release = try await service(json).catalogueRelease(releaseId: "release")
    #expect(release.songs[0].id == "catalogue-track")
    #expect(release.songs[0].track.id == "file-id")
    #expect(release.songs[0].track.sourceRevision == "v7")
    #expect(release.songs[0].track.trackNumber == 2)
    #expect(release.songs[1].availability == "requested")
    #expect(release.songs[1].track.serverState == "not_in_library")
  }
  @Test func groupsAndEditionsPreservePagingAndEditionMetadata() async throws {
    let groups = try await service(
      #"{"offset":50,"total":51,"releases":[{"id":"group","title":"Album","date":"2020","type":"Album"}]}"#
    ).catalogueGroups(artistId: "artist", offset: 50)
    #expect(groups.offset == 50)
    #expect(groups.total == 51)
    let editions = try await service(
      #"{"offset":0,"total":1,"editions":[{"id":"edition","title":"Album","date":"2020-01-01","country":"AU","description":"Deluxe","status":"Official","formats":["CD"],"track_count":12}]}"#
    ).catalogueEditions(groupId: groups.releases[0].id)
    #expect(editions.editions[0].trackCount == 12)
    #expect(editions.editions[0].description == "Deluxe")
  }
}
