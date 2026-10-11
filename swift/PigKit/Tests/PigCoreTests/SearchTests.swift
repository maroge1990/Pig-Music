import Foundation
import GRDB
import PigDomain
import PigStore
import PigSync
import Testing

@Test func indexedSearchPagesAllEntitiesAndTracksMutations() async throws {
  let store = try LibraryStore(path: ":memory:")
  let albums = try LibraryCodec.decoder().decode(
    [Album].self, from: Data(#"[{"id":"album","title":"Beyoncé album","artist":"Singer"}]"#.utf8))
  let artists = try LibraryCodec.decoder().decode(
    [Artist].self, from: Data(#"[{"id":"artist","name":"Beyoncé","album_ids":["album"]}]"#.utf8))
  let tracks = (0..<205).map {
    Track(id: String(format: "%03d", $0), title: "Beyoncé song", artist: "Singer")
  }
  try await store.replace(.init(revision: "one", tracks: tracks, albums: albums, artists: artists))
  var ids: [String] = []
  for offset in [0, 100, 200] {
    let page = try await store.searchPage(query: "Beyonce", offset: offset)
    #expect(page.revision == "one")
    #expect(page.nextOffset == (offset == 200 ? nil : offset + 100))
    ids += page.tracks.map(\.id)
    if offset == 0 {
      #expect(page.albums.map(\.id) == ["album"])
      #expect(page.artists.map(\.id) == ["artist"])
    }
  }
  #expect(ids.count == 205 && Set(ids).count == 205)
  #expect(try await store.albums(artistId: "artist").map(\.id) == ["album"])
  #expect(try await store.searchPage(query: "\" OR *").tracks.isEmpty)
  let delta = try LibraryCodec.decoder().decode(
    LibraryDelta.self,
    from: Data(
      #"{"revision":"two","upserts":{"tracks":[],"albums":[],"artists":[],"playlists":[]},"deletes":{"tracks":["000"],"albums":["album"],"artists":["artist"],"playlists":[]}}"#
        .utf8))
  try await store.apply(delta)
  let page = try await store.searchPage(query: "Beyonce")
  #expect(page.albums.isEmpty && page.artists.isEmpty)
  #expect(!page.tracks.contains { $0.id == "000" })
}

private actor DelayedSearch: CachedSearchSource {
  var waiting: CheckedContinuation<LibrarySearchPage, any Error>?
  var revision = "one"
  func searchPage(query: String, offset: Int, limit: Int) async throws -> LibrarySearchPage {
    if query == "old" { return try await withCheckedThrowingContinuation { waiting = $0 } }
    return LibrarySearchPage(
      tracks: [Track(id: "\(query)-\(offset)", title: query, artist: "Artist")], offset: offset,
      nextOffset: offset == 0 ? 100 : nil, revision: revision)
  }
  func ready() -> Bool { waiting != nil }
  func release() {
    waiting?.resume(
      returning: LibrarySearchPage(tracks: [Track(id: "old", title: "old", artist: "Artist")]))
    waiting = nil
  }
  func change() { revision = "two" }
}
private struct FailedCatalogue: OnlineSearchSource {
  func searchServer(query: String, offset: Int, revision: String?) async throws -> ServerSearchPage
  {
    try LibraryCodec.decoder().decode(
      ServerSearchPage.self,
      from: Data(
        #"{"tracks":[],"albums":[],"artists":[],"household_tracks":[{"id":"shared","title":"Song","artist":"Artist"}],"offset":0,"next_offset":null,"total_household_tracks":1,"revision":"server"}"#
          .utf8))
  }
  func catalogueArtists(query: String, offset: Int) async throws -> CatalogueArtistPage {
    throw NativeFailure.unavailable("Provider unavailable")
  }
}

@MainActor @Test func replacedSearchAndAccountClearDiscardLateResults() async throws {
  let source = DelayedSearch()
  let session = SearchSession(cached: source)
  let old = Task { await session.search("old") }
  while !(await source.ready()) { await Task.yield() }
  await session.search("new")
  await source.release()
  await old.value
  #expect(session.tracks.map(\.id) == ["new-0"])
  let pending = Task { await session.search("old") }
  while !(await source.ready()) { await Task.yield() }
  session.clear()
  await source.release()
  await pending.value
  #expect(session.query.isEmpty && session.tracks.isEmpty && !session.localLoading)
}
@MainActor @Test func providerFailurePreservesLocalAndHouseholdAndRevisionChangeRejectsAppend()
  async throws
{
  let source = DelayedSearch()
  let session = SearchSession(cached: source, online: FailedCatalogue())
  await session.search("Song")
  #expect(session.tracks.count == 1 && session.household.map(\.id) == ["shared"])
  #expect(session.catalogueError == "Provider unavailable")
  await source.change()
  await session.moreLocal()
  #expect(session.tracks.count == 1 && session.localError != nil)
}

@Test func upgradedCacheBuildsEntityIndexesAndRenamedRowsReplaceOldTerms() async throws {
  let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
  defer { try? FileManager.default.removeItem(at: directory) }
  let path = directory.appendingPathComponent("library.sqlite").path
  let previous = try LibraryStore(path: path)
  let snapshot = try LibraryCodec.decoder().decode(
    LibrarySnapshot.self,
    from: Data(
      #"{"revision":"one","tracks":[],"albums":[{"id":"album","title":"Oldname","artist":"Artist"}],"artists":[{"id":"artist","name":"Oldname","album_ids":["album"]}],"playlists":[]}"#
        .utf8))
  try await previous.replace(snapshot)
  // Recreate a v2 on-disk cache so migration must index existing albums/artists.
  let queue = try DatabaseQueue(path: path)
  try await queue.write { db in
    try db.execute(sql: "DROP TABLE album_search")
    try db.execute(sql: "DROP TABLE artist_search")
    try db.execute(sql: "DELETE FROM grdb_migrations WHERE identifier='entity-search-v3'")
  }
  try queue.close()
  let upgraded = try LibraryStore(path: path)
  let existing = try await upgraded.searchPage(query: "Oldname")
  #expect(existing.albums.count == 1 && existing.artists.count == 1)
  let delta = try LibraryCodec.decoder().decode(
    LibraryDelta.self,
    from: Data(
      #"{"revision":"two","upserts":{"tracks":[],"albums":[{"id":"album","title":"Newname","artist":"Artist"}],"artists":[{"id":"artist","name":"Newname","album_ids":["album"]}],"playlists":[]},"deletes":{"tracks":[],"albums":[],"artists":[],"playlists":[]}}"#
        .utf8))
  try await upgraded.apply(delta)
  let old = try await upgraded.searchPage(query: "Oldname")
  #expect(old.albums.isEmpty && old.artists.isEmpty)
  let renamed = try await upgraded.searchPage(query: "Newname")
  #expect(renamed.albums.count == 1 && renamed.artists.count == 1)
}

private struct ExpiredSearch: OnlineSearchSource {
  func searchServer(query: String, offset: Int, revision: String?) async throws -> ServerSearchPage
  { throw NativeFailure.authentication }
  func catalogueArtists(query: String, offset: Int) async throws -> CatalogueArtistPage {
    throw NativeFailure.unavailable("Provider failed")
  }
}
@MainActor @Test func expiredSearchClearsAllResultsAndNotifiesAccountOnce() async {
  var callbacks = 0
  let session = SearchSession(
    cached: DelayedSearch(), online: ExpiredSearch(), onAuthentication: { callbacks += 1 })
  await session.search("Song")
  #expect(callbacks == 1)
  #expect(
    session.tracks.isEmpty && session.household.isEmpty && session.catalogue.isEmpty
      && session.query.isEmpty)
}
