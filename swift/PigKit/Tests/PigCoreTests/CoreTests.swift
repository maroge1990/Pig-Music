import Foundation
import PigDomain
import PigPlayback
import PigStore
import PigSync
import Testing

@Test func queueKeepsRepeatedOccurrencesAndPreviousRestarts() {
  let song = Track(id: "same", title: "Song", artist: "Artist")
  var queue = PlaybackQueue()
  queue.replace([song, song])
  #expect(queue.items[0].id != queue.items[1].id)
  let advanced = queue.next()
  #expect(advanced)
  let restarted = queue.previous(elapsed: 4)
  #expect(restarted)
  #expect(queue.index == 1)
  let previous = queue.previous(elapsed: 1)
  #expect(!previous)
  #expect(queue.index == 0)
}

@Test func transitionRendererPreservesBoundaryAndBoundsOverlap() {
  let first: [Float] = [0.1, 0.2, 0.3]
  let second: [Float] = [0.4, 0.5, 0.6]
  #expect(TransitionPlanner.render(first, second, overlapFrames: 0) == first + second)
  let unity = TransitionPlanner.render([1, 1, 1], [1, 1, 1], overlapFrames: 2)
  #expect(unity == [1, 1, 1, 1])
  #expect(TransitionPlanner.mode(crossfade: true, albumOrder: true) == .gapless)
  #expect(TransitionPlanner.mode(crossfade: true, albumOrder: false) == .crossfade(seconds: 3))
}

@Test func namespaceSeparatesPersonAndServerPort() {
  let first = URL(string: "https://music.example:10000")!
  #expect(
    LibraryNamespace.key(server: first, personId: "a")
      != LibraryNamespace.key(server: first, personId: "b"))
  #expect(
    LibraryNamespace.key(server: first, personId: "a")
      != LibraryNamespace.key(server: URL(string: "https://music.example")!, personId: "a"))
}

@Test func cloudPlaylistEntryPreservesEditionContextAndOccurrenceIdentity() throws {
  let entry = try LibraryCodec.decoder().decode(
    PlaylistEntry.self,
    from: Data(
      #"{"entry_id":"occurrence","position":2,"title":"Live Song","artist":"Artist","album":"Live Edition","album_artist":"Artist","duration":180,"disc_number":2,"track_number":3,"musicbrainz_release_id":"release","musicbrainz_recording_id":"recording","saved_track":null}"#
        .utf8))
  #expect(entry.id == "occurrence")
  #expect(entry.album == "Live Edition")
  #expect(entry.musicbrainzReleaseId == "release")
  #expect(entry.musicbrainzRecordingId == "recording")
  #expect(entry.discNumber == 2)
  #expect(entry.trackNumber == 3)
  #expect(entry.savedTrack == nil)
}

@Test func storeReplacesAndAppliesDeletesAtomicallyAndSearchesUnicode() async throws {
  let store = try LibraryStore(path: ":memory:")
  try await store.replace(
    .init(
      revision: "one",
      tracks: [
        Track(id: "a", title: "Beyoncé", artist: "Artist"),
        Track(id: "b", title: "Other", artist: "Artist"),
      ]))
  #expect(try await store.tracks(query: "Beyonce").map(\.id) == ["a"])
  let delta = try LibraryCodec.decoder().decode(
    LibraryDelta.self,
    from: Data(
      #"{"revision":"two","upserts":{"tracks":[{"id":"c","title":"New","artist":"Artist"}],"albums":[],"artists":[],"playlists":[]},"deletes":{"tracks":["a"],"albums":[],"artists":[],"playlists":[]}}"#
        .utf8))
  try await store.apply(delta)
  #expect(try await store.revision() == "two")
  #expect(try await store.count(.tracks) == 2)
  #expect(try await store.tracks(query: "Beyonce").isEmpty)
  #expect(try await store.tracks(query: "\" OR *").isEmpty)
}

@Test func storeSeparatesAlbumCategoriesAndHidesCompilationOnlyArtists() async throws {
  let store = try LibraryStore(path: ":memory:")
  let snapshot = try LibraryCodec.decoder().decode(
    LibrarySnapshot.self,
    from: Data(
      #"{"revision":"one","tracks":[],"playlists":[],"albums":[{"id":"a","title":"Own","artist":"Band","category":"album"},{"id":"m","title":"Show","artist":"Cast","category":"musical"},{"id":"c","title":"Hits","artist":"Various","category":"compilation"},{"id":"u","title":"Legacy","artist":"Band"}],"artists":[{"id":"band","name":"Band"},{"id":"guest","name":"Guest","compilation_only":true}]}"#
        .utf8))
  try await store.replace(snapshot)
  #expect(try await store.albums().map(\.id) == ["u", "a"])
  #expect(try await store.albums(category: "musical").map(\.id) == ["m"])
  #expect(try await store.albumCategoryCounts() == ["album": 2, "musical": 1, "compilation": 1])
  #expect(try await store.artists().map(\.id) == ["band"])
  #expect(try await store.ownArtistCount() == 1)
}

private actor FailedSource: LibrarySource {
  func bootstrap() async throws -> LibrarySnapshot { throw NativeFailure.unavailable("offline") }
  func changes(since: String) async throws -> LibraryDelta { throw NativeFailure.resync }
}

@Test func failedResyncRetainsLastValidOfflineLibrary() async throws {
  let store = try LibraryStore(path: ":memory:")
  try await store.replace(
    .init(revision: "valid", tracks: [Track(id: "a", title: "Kept", artist: "Artist")]))
  do {
    try await SyncCoordinator(source: FailedSource(), store: store).refresh()
    Issue.record("Expected sync failure")
  } catch NativeFailure.unavailable {}
  #expect(try await store.revision() == "valid")
  #expect(try await store.tracks().first?.title == "Kept")
}
