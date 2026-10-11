import Foundation
import PigAPI
import PigDomain

public enum NativeFailure: Error, LocalizedError, Sendable, Equatable {
  case authentication, resync, changed
  case unavailable(String)
  case invalidMediaURL
  public var errorDescription: String? {
    switch self {
    case .authentication: "Please sign in again. This device session is no longer available."
    case .resync: "Your library needs a fresh sync."
    case .changed: "Your library changed during sync. Please try again."
    case .unavailable(let message): message
    case .invalidMediaURL: "The server returned an unsupported playback address."
    }
  }
}

public protocol LibrarySource: Sendable {
  func bootstrap() async throws -> LibrarySnapshot
  func changes(since: String) async throws -> LibraryDelta
}

public actor NativeService: LibrarySource {
  private let client: Client
  public let server: URL
  private let vault: any DeviceTokenStore
  private let artworkTransport: ArtworkTransport
  public init(server: String, vault: any DeviceTokenStore) throws {
    self.server = try ServerAddress.validate(server)
    self.vault = vault
    artworkTransport = ArtworkTransport(server: self.server, vault: vault)
    client = try PigClient.make(server: server, vault: vault)
  }
  // Injectable generated client for isolated transport/fixture tests, not an app URL bypass.
  init(server: URL, client: Client, vault: any DeviceTokenStore) {
    self.server = server
    self.client = client
    self.vault = vault
    artworkTransport = ArtworkTransport(server: server, vault: vault)
  }
  public func artwork(_ request: ArtworkRequest) async throws -> Data {
    try await artworkTransport.fetch(request)
  }
  public func signIn(username: String, password: String, deviceName: String) async throws -> Person
  {
    let response = try await client.device_api_v1_auth_device_post(
      .init(
        body: .json(
          .init(device_name: deviceName, password: password, platform: .ios, username: username))))
    switch response {
    case .ok(let success):
      let session = try success.body.json
      try await vault.save(session.token)
      return try LibraryCodec.convert(session.user)
    case .unauthorized:
      throw NativeFailure.unavailable("The username or password was not accepted.")
    case .tooManyRequests:
      throw NativeFailure.unavailable("Too many sign-in attempts. Please wait and try again.")
    case .serviceUnavailable:
      throw NativeFailure.unavailable(
        "The administrator needs to finish server setup, or the server is unavailable.")
    default:
      throw NativeFailure.unavailable("Sign-in failed. Check the server address and try again.")
    }
  }
  public func me() async throws -> Person {
    switch try await client.me_api_v1_me_get(.init()) {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable("Can't reach your account. Check Tailscale and try again.")
    }
  }
  public func signOut() async throws {
    let result = try await client.logout_api_v1_auth_logout_post(.init())
    switch result {
    case .ok, .unauthorized: try await vault.clear()
    default:
      throw NativeFailure.unavailable("Couldn't revoke this session. Reconnect and try again.")
    }
  }

  public func home(_ section: HomeSection) async throws -> HomeContent {
    switch section {
    case .recent:
      switch try await client.recent_api_v1_home_recent_get(.init()) {
      case .ok(let response):
        return HomeContent(
          albums: try response.body.json.albums.map {
            try LibraryCodec.convert($0, to: Album.self)
          })
      case .unauthorized: throw NativeFailure.authentication
      default:
        throw NativeFailure.unavailable(
          "Recently added albums are unavailable. Your cached library is still accessible.")
      }
    case .popular:
      switch try await client.popular_api_v1_home_popular_get(.init()) {
      case .ok(let response): return HomeContent(feed: try LibraryCodec.convert(response.body.json))
      case .unauthorized: throw NativeFailure.authentication
      default: throw NativeFailure.unavailable("Popular music is unavailable. Try again shortly.")
      }
    case .recommended:
      switch try await client.recommended_api_v1_home_recommended_get(.init()) {
      case .ok(let response): return HomeContent(feed: try LibraryCodec.convert(response.body.json))
      case .unauthorized: throw NativeFailure.authentication
      default:
        throw NativeFailure.unavailable(
          "Recommendations are unavailable. Your library is still accessible.")
      }
    }
  }

  public func catalogueGroups(artistId: String, offset: Int = 0) async throws -> CatalogueGroups {
    switch try await client.groups_api_v1_catalogue_artists__artist_id__releases_get(
      .init(path: .init(artist_id: artistId), query: .init(offset: offset)))
    {
    case .ok(let response): return try LibraryCodec.convert(response.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable("The artist catalogue is unavailable. Try again shortly.")
    }
  }
  public func catalogueEditions(groupId: String, offset: Int = 0) async throws -> CatalogueEditions
  {
    switch try await client.editions_api_v1_catalogue_groups__group_id__editions_get(
      .init(path: .init(group_id: groupId), query: .init(offset: offset)))
    {
    case .ok(let response): return try LibraryCodec.convert(response.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Album editions are unavailable. Try again shortly.")
    }
  }
  public func catalogueRelease(releaseId: String) async throws -> CatalogueRelease {
    switch try await client.release_api_v1_catalogue_releases__release_id__get(
      .init(path: .init(release_id: releaseId)))
    {
    case .ok(let response):
      let value = try response.body.json
      let songs = try value.tracks.map { item in
        var track: Track
        if let saved = item.saved_track {
          track = try LibraryCodec.convert(saved)
        } else {
          track = try LibraryCodec.convert(item)
        }
        // Household and requested songs still require remote resolution, never file access.
        if item.saved_track == nil { track.serverState = "not_in_library" }
        track.trackNumber = item.track_number
        track.discNumber = item.disc_number
        return CatalogueSong(
          id: item.id, track: track, availability: item.server_state?.rawValue ?? "not_in_library")
      }
      return CatalogueRelease(id: value.id, title: value.title, artist: value.artist, songs: songs)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("This album is unavailable. Try again shortly.")
    }
  }

  public func bootstrap() async throws -> LibrarySnapshot {
    var snapshot = LibrarySnapshot(revision: "")
    var cursor: String?
    repeat {
      try Task.checkCancellation()
      switch try await client.tracks_api_v1_library_tracks_get(
        .init(query: .init(cursor: cursor, limit: 200)))
      {
      case .ok(let success):
        let page = try success.body.json
        try check(page.revision, snapshot: &snapshot)
        snapshot.tracks += try page.items.map { try LibraryCodec.convert($0, to: Track.self) }
        cursor = page.next_cursor
      case .unauthorized: throw NativeFailure.authentication
      case .conflict: throw NativeFailure.changed
      default: throw NativeFailure.unavailable("Unable to sync songs.")
      }
    } while cursor != nil
    repeat {
      try Task.checkCancellation()
      switch try await client.albums_api_v1_library_albums_get(
        .init(query: .init(cursor: cursor, limit: 200)))
      {
      case .ok(let success):
        let page = try success.body.json
        try check(page.revision, snapshot: &snapshot)
        snapshot.albums += try page.items.map { try LibraryCodec.convert($0, to: Album.self) }
        cursor = page.next_cursor
      case .unauthorized: throw NativeFailure.authentication
      case .conflict: throw NativeFailure.changed
      default: throw NativeFailure.unavailable("Unable to sync albums.")
      }
    } while cursor != nil
    repeat {
      try Task.checkCancellation()
      switch try await client.artists_api_v1_library_artists_get(
        .init(query: .init(cursor: cursor, limit: 200)))
      {
      case .ok(let success):
        let page = try success.body.json
        try check(page.revision, snapshot: &snapshot)
        snapshot.artists += try page.items.map { try LibraryCodec.convert($0, to: Artist.self) }
        cursor = page.next_cursor
      case .unauthorized: throw NativeFailure.authentication
      case .conflict: throw NativeFailure.changed
      default: throw NativeFailure.unavailable("Unable to sync artists.")
      }
    } while cursor != nil
    switch try await client.playlists_api_v1_playlists_get(.init()) {
    case .ok(let success):
      for summary in try success.body.json.playlists {
        switch try await client.playlist_api_v1_playlists__playlist_id__get(
          .init(path: .init(playlist_id: summary.id)))
        {
        case .ok(let detail): snapshot.playlists.append(try LibraryCodec.convert(detail.body.json))
        case .notFound: throw NativeFailure.changed
        case .unauthorized: throw NativeFailure.authentication
        default: throw NativeFailure.unavailable("Unable to sync playlists.")
        }
      }
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Unable to sync playlists.")
    }
    // Close the read/mutation window before publishing any bootstrap data.
    let delta = try await changes(since: snapshot.revision)
    snapshot.tracks = merge(
      snapshot.tracks, upserts: delta.upserts.tracks, deletes: delta.deletes.tracks)
    snapshot.albums = merge(
      snapshot.albums, upserts: delta.upserts.albums, deletes: delta.deletes.albums)
    snapshot.artists = merge(
      snapshot.artists, upserts: delta.upserts.artists, deletes: delta.deletes.artists)
    snapshot.playlists = merge(
      snapshot.playlists, upserts: delta.upserts.playlists, deletes: delta.deletes.playlists)
    snapshot.revision = delta.revision
    return snapshot
  }
  private func check(_ revision: String, snapshot: inout LibrarySnapshot) throws {
    if snapshot.revision.isEmpty { snapshot.revision = revision }
    guard snapshot.revision == revision else { throw NativeFailure.changed }
  }
  private func merge<T: Identifiable>(_ current: [T], upserts: [T], deletes: [String]) -> [T]
  where T.ID == String {
    var values: [String: T] = [:]
    for value in current { values[value.id] = value }
    for id in deletes { values.removeValue(forKey: id) }
    for value in upserts { values[value.id] = value }
    return Array(values.values)
  }
  public func changes(since: String) async throws -> LibraryDelta {
    switch try await client.changes_api_v1_library_changes_get(.init(query: .init(since: since))) {
    case .ok(let success): return try LibraryCodec.convert(success.body.json)
    case .gone: throw NativeFailure.resync
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Unable to refresh your library.")
    }
  }
  public func playbackURL(trackId: String) async throws -> URL {
    switch try await client.playback_url_api_v1_playback__track_id__url_post(
      .init(path: .init(track_id: trackId)))
    {
    case .ok(let success):
      let result = try success.body.json
      guard let url = URL(string: result.url, relativeTo: server)?.absoluteURL,
        url.scheme == server.scheme, url.host == server.host, url.port == server.port,
        url.user == nil, url.password == nil
      else { throw NativeFailure.invalidMediaURL }
      return url
    case .unauthorized: throw NativeFailure.authentication
    case .notFound:
      throw NativeFailure.unavailable("This song is no longer available on the server.")
    default: throw NativeFailure.unavailable("Unable to prepare this song for playback.")
    }
  }
  public func resolve(_ track: Track) async throws -> URL {
    if track.serverState != "not_in_library" { return try await playbackURL(trackId: track.id) }
    let response = try await client.playback_remote_api_v1_remote_playback_post(
      .init(
        body: .json(
          .init(
            album: track.album, album_artist: track.albumArtist, artist: track.artist,
            disc_number: track.discNumber, duration: track.duration,
            musicbrainz_recording_id: track.musicbrainzRecordingId,
            musicbrainz_release_id: track.musicbrainzReleaseId, title: track.title,
            track_number: track.trackNumber))))
    struct Remote: Decodable { let url: String }
    switch response {
    case .ok(let success):
      let remote: Remote = try LibraryCodec.convert(success.body.json)
      guard let url = URL(string: remote.url), url.scheme == "https", url.host != nil,
        url.user == nil, url.password == nil
      else { throw NativeFailure.invalidMediaURL }
      return url
    case .unauthorized: throw NativeFailure.authentication
    case .conflict:
      throw NativeFailure.unavailable(
        "Remote streaming is disabled. You can still play saved songs or request this song using the web app."
      )
    case .notFound:
      throw NativeFailure.unavailable(
        "No reliable remote stream matched this song. Saved music is still available.")
    default:
      throw NativeFailure.unavailable(
        "Remote streaming is unavailable. Try again or play a saved song.")
    }
  }
}
