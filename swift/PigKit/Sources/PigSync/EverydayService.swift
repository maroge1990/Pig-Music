import Foundation
import OpenAPIRuntime
import PigAPI
import PigDomain

extension NativeService {
  public func hideMix(_ id: String) async throws {
    switch try await client.hide_mix_api_v1_mixes__edition_id__hide_post(
      .init(path: .init(edition_id: id)))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Unable to hide this edition. Try again.")
    }
  }
  public func saveMix(_ id: String) async throws -> Playlist {
    switch try await client.save_mix_api_v1_mixes__edition_id__save_post(
      .init(path: .init(edition_id: id)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Unable to save this mix. Try again.")
    }
  }
  public func hideMixSong(_ trackId: String) async throws {
    switch try await client.hide_mix_song_api_v1_mixes_hide_post(
      .init(body: .json(.init(track_id: trackId))))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Unable to hide this song. Try again.")
    }
  }
  public func radio(after: String?) async throws -> RadioBatch {
    switch try await client.radio_api_v1_radio_get(.init(query: .init(after: after))) {
    case .ok(let value): return try LibraryCodec.convert(value.body.json, to: RadioBatch.self)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Your radio is unavailable. Try again shortly.")
    }
  }
  public func radioFeedback(trackId: String, action: String) async throws {
    switch try await client.radio_feedback_api_v1_radio_feedback_post(
      .init(body: .json(.init(action: action, track_id: trackId))))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Unable to update your radio. Try again.")
    }
  }
  public func applyMutation(_ mutation: OfflineMutation) async throws -> OfflineMutationReceipt {
    guard
      var json = try JSONSerialization.jsonObject(with: LibraryCodec.encoder().encode(mutation))
        as? [String: Any]
    else { throw MutationRejection.rejected }
    if var track = json["track"] as? [String: Any], let year = mutation.track?.year {
      track["year"] = year.text
      json["track"] = track
    }
    let payload = try JSONDecoder().decode(
      Components.Schemas.NativeMutationInput.self,
      from: JSONSerialization.data(withJSONObject: json))
    switch try await client.native_mutation_api_v1_mutations_post(.init(body: .json(payload))) {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    case .conflict: throw NativeFailure.changed
    case .badRequest, .notFound, .unprocessableContent: throw MutationRejection.rejected
    default:
      throw NativeFailure.unavailable(
        "Your edits are saved on this phone and will retry when the server is available.")
    }
  }

  public func artistAcquisition(id: String) async throws -> ArtistAcquisition {
    switch try await client.artist_acquisition_api_v1_artists__artist_id__acquisition_get(
      .init(path: .init(artist_id: id)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Artist requests are unavailable.")
    }
  }
  public func configureArtist(id: String, kinds: [String], monitor: Bool, request: Bool)
    async throws -> ArtistAcquisition
  {
    let selected = try kinds.map { kind in
      guard
        let value = Components.Schemas.server__routes__personal__ArtistRequest.kindsPayloadPayload(
          rawValue: kind)
      else { throw NativeFailure.unavailable("Choose a supported release type.") }
      return value
    }
    switch try await client.configure_artist_api_v1_artists__artist_id__acquisition_put(
      .init(
        path: .init(artist_id: id),
        body: .json(.init(kinds: selected, monitor: monitor, request: request))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Artist settings were not confirmed. Refresh before trying again.")
    }
  }
  public func cancelArtist(id: String) async throws -> ArtistAcquisition {
    switch try await client.cancel_artist_api_v1_artists__artist_id__acquisition_delete(
      .init(path: .init(artist_id: id)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable("Cancellation was not confirmed. Refresh artist requests.")
    }
  }
  public func cancelRequest(id: String) async throws -> CancelledRequest {
    switch try await client.cancel_request_api_v1_requests__request_id__cancel_post(
      .init(path: .init(request_id: id)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Cancellation was not confirmed. Refresh requests before trying again.")
    }
  }
  public func retryRequest(id: String) async throws {
    switch try await client.retry_request_api_v1_requests__request_id__retry_post(
      .init(path: .init(request_id: id)))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Retry was not confirmed. Refresh requests before trying again.")
    }
  }

  public func recordListens(_ events: [ListeningEvent]) async throws {
    guard !events.isEmpty else { return }
    let payload = events.map {
      Components.Schemas.PlayEvent(
        event_id: $0.eventId, played_at: $0.playedAt, seconds: $0.seconds, track_id: $0.trackId)
    }
    switch try await client.play_events_api_v1_play_events_post(
      .init(body: .json(.init(events: payload))))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Listening history will retry on the next connection.")
    }
  }

  public func previewImport(_ data: Data) async throws -> ImportPreview {
    switch try await client.preview_import_api_v1_imports_apple_preview_post(
      .init(body: .xml(HTTPBody(data))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "The export could not be reviewed. Check the Apple Music XML file.")
    }
  }

  public func playlist(id: String) async throws -> Playlist {
    switch try await client.playlist_api_v1_playlists__playlist_id__get(
      .init(path: .init(playlist_id: id)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("This playlist is unavailable. Refresh your library.")
    }
  }
  public func createPlaylist(name: String) async throws -> Playlist {
    switch try await client.create_api_v1_playlists_post(.init(body: .json(.init(name: name)))) {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Creation was not confirmed. Refresh playlists before trying again.")
    }
  }
  public func addToPlaylist(id: String, track: Track) async throws -> Playlist {
    switch try await client.add_song_api_v1_playlists__playlist_id__songs_post(
      .init(
        path: .init(playlist_id: id), query: .init(allow_repeat: true), body: .json(input(track))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Addition was not confirmed. Refresh this playlist before trying again.")
    }
  }
  public func editPlaylist(id: String, revision: Int, name: String? = nil, order: [Int]? = nil)
    async throws -> Playlist
  {
    switch try await client.edit_api_v1_playlists__playlist_id__patch(
      .init(
        path: .init(playlist_id: id),
        body: .json(.init(name: name, order: order, revision: revision))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    case .conflict: throw NativeFailure.changed
    default:
      throw NativeFailure.unavailable("The edit was not confirmed. Refresh before reapplying it.")
    }
  }
  public func removePlaylistEntry(id: String, revision: Int, position: Int) async throws -> Playlist
  {
    switch try await client.remove_song_api_v1_playlists__playlist_id__songs__position__delete(
      .init(path: .init(playlist_id: id, position: position), query: .init(revision: revision)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    case .conflict: throw NativeFailure.changed
    default: throw NativeFailure.unavailable("Removal was not confirmed. Refresh this playlist.")
    }
  }
  public func deletePlaylist(id: String, revision: Int) async throws {
    switch try await client.delete_api_v1_playlists__playlist_id__delete(
      .init(path: .init(playlist_id: id), query: .init(revision: revision)))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    case .conflict: throw NativeFailure.changed
    default: throw NativeFailure.unavailable("Deletion was not confirmed. Refresh playlists.")
    }
  }
  public func importApple(_ data: Data) async throws -> ImportResult {
    switch try await client.import_apple_api_v1_imports_apple_post(
      .init(body: .xml(HTTPBody(data))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Import was not confirmed. Check the XML export and refresh playlists.")
    }
  }
  public func preferences() async throws -> AccountPreferences {
    switch try await client.preferences_api_v1_preferences_get(.init()) {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Preferences are unavailable.")
    }
  }
  public func savePreferences(_ value: AccountPreferences) async throws -> AccountPreferences {
    guard
      let appearance = Components.Schemas.Preferences.appearancePayload(rawValue: value.appearance),
      let tab = Components.Schemas.Preferences.default_tabPayload(rawValue: value.defaultTab)
    else { throw NativeFailure.unavailable("Choose supported preferences.") }
    switch try await client.save_preferences_api_v1_preferences_put(
      .init(body: .json(.init(appearance: appearance, default_tab: tab))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Preferences were not confirmed.")
    }
  }
  public func sessions() async throws -> [AccountSession] {
    switch try await client.sessions_api_v1_me_sessions_get(.init()) {
    case .ok(let value):
      return try LibraryCodec.convert(value.body.json, to: AccountSessions.self).sessions
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Your sessions are unavailable.")
    }
  }
  public func revokeSession(id: String) async throws {
    switch try await client.revoke_api_v1_me_sessions__identity__delete(
      .init(path: .init(identity: id)))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Revocation was not confirmed.")
    }
  }
  public func changePassword(current: String, password: String) async throws {
    switch try await client.password_api_v1_me_password_post(
      .init(body: .json(.init(current_password: current, password: password))))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Password was not changed. Check your current password and use at least 12 characters.")
    }
  }
  public func quality() async throws -> QualitySettings {
    switch try await client.quality_api_v1_quality_get(.init()) {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Quality preferences are unavailable.")
    }
  }
  public func saveQuality(scope: String, id: String, preferred: String?) async throws {
    guard let scope = Components.Schemas.QualityPreference.scopePayload(rawValue: scope) else {
      throw NativeFailure.unavailable("Choose a supported quality scope.")
    }
    switch try await client.save_quality_api_v1_quality_put(
      .init(
        body: .json(
          .init(
            item_id: id,
            preferred: preferred.flatMap {
              Components.Schemas.QualityPreference.preferredPayload(rawValue: $0)
            }, scope: scope))))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Quality preference was not confirmed.")
    }
  }
  public func removalPreview(ids: [String]) async throws -> RemovalPreview {
    switch try await client.preview_removal_api_v1_library_removal_preview_post(
      .init(body: .json(.init(track_ids: ids))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable("Removal preview is unavailable. Refresh your library.")
    }
  }
  public func removeMusic(ids: [String], confirmation: String) async throws -> RemovalResult {
    switch try await client.remove_music_api_v1_library_remove_post(
      .init(body: .json(.init(confirmation: confirmation, track_ids: ids))))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    case .conflict: throw NativeFailure.changed
    default: throw NativeFailure.unavailable("Removal was not confirmed. Refresh your library.")
    }
  }
  public func undoRemoval(id: String) async throws {
    switch try await client.undo_removal_api_v1_library_removals__operation_id__undo_post(
      .init(path: .init(operation_id: id)))
    {
    case .ok: return
    case .unauthorized: throw NativeFailure.authentication
    default:
      throw NativeFailure.unavailable(
        "Undo unavailable or expired. Ask the administrator to check Recovery.")
    }
  }
}

extension NativeService: DeviceCopySource {
  public func deviceCopy(trackId: String, quality: String, create: Bool) async throws -> DeviceCopy
  {
    if create {
      switch try await client.request_copy_api_v1_tracks__track_id__copy_post(
        .init(
          path: .init(track_id: trackId), query: .init(quality: quality == "aac" ? .aac : .original)
        ))
      {
      case .ok(let value): return try LibraryCodec.convert(value.body.json)
      case .unauthorized: throw NativeFailure.authentication
      default: throw NativeFailure.unavailable("The server could not prepare this device copy.")
      }
    }
    switch try await client.copy_status_api_v1_tracks__track_id__copy_get(
      .init(
        path: .init(track_id: trackId), query: .init(quality: quality == "aac" ? .aac : .original)))
    {
    case .ok(let value): return try LibraryCodec.convert(value.body.json)
    case .unauthorized: throw NativeFailure.authentication
    default: throw NativeFailure.unavailable("Device copy status is unavailable.")
    }
  }
  public func copyRequest(trackId: String, quality: String) async throws -> URLRequest {
    guard let token = try await vault.read() else { throw NativeFailure.authentication }
    let segment = trackId.addingPercentEncoding(
      withAllowedCharacters: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_.")))!
    var components = URLComponents(url: server, resolvingAgainstBaseURL: false)!
    components.percentEncodedPath = "/api/v1/tracks/" + segment + "/copy/file"
    components.queryItems = [
      URLQueryItem(name: "quality", value: quality == "aac" ? "aac" : "original")
    ]
    var request = URLRequest(url: components.url!)
    request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization")
    return request
  }
}
