import Foundation
import PigDomain
import PigStore
import Testing

struct LibrarySortingTests {
  @Test func sortingPagesAcrossTheWholeCacheAndKeepsAlbumSequence() async throws {
    let store = try LibraryStore(path: ":memory:")
    let tracks = (0..<250).map { index in
      var track = Track(
        id: String(index), title: String(format: "%03d", index), artist: index % 2 == 0 ? "A" : "B")
      track.albumId = "album"
      track.trackNumber = index + 1
      return track
    }
    try await store.replace(LibrarySnapshot(revision: "one", tracks: tracks))
    let first = try await store.tracks(limit: 100, sort: .artist)
    let next = try await store.tracks(offset: 100, limit: 100, sort: .artist)
    #expect(first.allSatisfy { $0.artist == "A" })
    #expect(next.prefix(25).allSatisfy { $0.artist == "A" })
    #expect(next.dropFirst(25).allSatisfy { $0.artist == "B" })
    #expect(Set((first + next).map(\.id)).count == 200)
    #expect(try await store.tracks(limit: 1, sort: .titleDescending).first?.id == "249")
    #expect(
      try await store.tracks(albumId: "album", sort: .titleDescending).map(\.id) == tracks.map(\.id)
    )
  }
  @Test func aLeadingTheIsIgnoredWhenSorting() async throws {
    #expect("The Beatles".sortingName == "Beatles")
    #expect("The".sortingName == "The")
    #expect("Theatre".sortingName == "Theatre")
    let store = try LibraryStore(path: ":memory:")
    let names = ["The Cure", "ABBA", "the Beatles", "Coldplay", "Theory", "2Pac", "10cc"]
    let tracks = names.enumerated().map { index, name in
      Track(id: String(index), title: name, artist: name)
    }
    try await store.replace(LibrarySnapshot(revision: "one", tracks: tracks))
    let expected = ["2Pac", "10cc", "ABBA", "the Beatles", "Coldplay", "The Cure", "Theory"]
    #expect(try await store.tracks(limit: 10, sort: .title).map(\.title) == expected)
    #expect(try await store.tracks(limit: 10, sort: .artist).map(\.artist) == expected)
    #expect(names.sorted { $0.sortingCompare($1) == .orderedAscending } == expected)
  }
}

struct SourceRevisionLookupTests {
  @Test func oneQueryMatchesPerTrackLookups() async throws {
    let store = try LibraryStore(path: ":memory:")
    let tracks = (0..<600).map { index in
      var track = Track(id: "t\(index)", title: "Song \(index)", artist: "A")
      track.sourceRevision = index % 3 == 0 ? nil : "rev\(index)"
      return track
    }
    try await store.replace(LibrarySnapshot(revision: "one", tracks: tracks))
    let ids = tracks.map(\.id) + ["missing", "also-missing"]
    let batched = try await store.sourceRevisions(ids: ids)
    var single: [String: String?] = [:]
    for id in ids {
      if let track = try await store.track(id: id) {
        single.updateValue(track.sourceRevision, forKey: id)
      }
    }
    #expect(batched == single)
    #expect(batched.count == 600)
    #expect(batched["t3"] == .some(nil))
    #expect(batched["t4"] == .some("rev4"))
    #expect(batched["missing"] == nil)
    #expect(try await store.sourceRevisions(ids: [String]()).isEmpty)
  }
}

struct ArtworkRevisionTests {
  private func delta(_ revision: String, upserts: String, deletedAlbums: String = "")
    throws -> LibraryDelta
  {
    try LibraryCodec.decoder().decode(
      LibraryDelta.self,
      from: Data(
        #"{"revision":"\#(revision)","upserts":{\#(upserts)},"deletes":{"tracks":[],"albums":[\#(deletedAlbums)],"artists":[],"playlists":[]}}"#
          .utf8))
  }
  @Test func onlyCoverChangesMoveTheArtworkRevision() async throws {
    let store = try LibraryStore(path: ":memory:")
    #expect(try await store.artworkRevision() == nil)
    let album = #"{"id":"al","title":"Album","artist":"A","cover_sha":"aaa"}"#
    try await store.apply(
      delta("one", upserts: #""tracks":[],"albums":[\#(album)],"artists":[],"playlists":[]"#))
    let first = try #require(try await store.artworkRevision())
    // A title change and a new song without a cover leave covers alone.
    try await store.apply(
      delta(
        "two",
        upserts:
          #""tracks":[{"id":"t","title":"Song","artist":"A"}],"albums":[{"id":"al","title":"Renamed","artist":"A","cover_sha":"aaa"}],"artists":[],"playlists":[]"#
      ))
    #expect(try await store.revision() == "two")
    #expect(try await store.artworkRevision() == first)
    // A changed cover moves it.
    try await store.apply(
      delta(
        "three",
        upserts:
          #""tracks":[],"albums":[{"id":"al","title":"Renamed","artist":"A","cover_sha":"bbb"}],"artists":[],"playlists":[]"#
      ))
    let second = try #require(try await store.artworkRevision())
    #expect(second != first)
    // An artist's chosen cover album moves it; repeating it does not.
    let artist =
      #""tracks":[],"albums":[],"artists":[{"id":"ar","name":"A","cover_album_id":"al"}],"playlists":[]"#
    try await store.apply(delta("four", upserts: artist))
    let third = try #require(try await store.artworkRevision())
    #expect(third != second)
    try await store.apply(delta("five", upserts: artist))
    #expect(try await store.artworkRevision() == third)
    // A removed album can change an artist's cover.
    try await store.apply(
      delta(
        "six", upserts: #""tracks":[],"albums":[],"artists":[],"playlists":[]"#,
        deletedAlbums: #""al""#))
    let fourth = try #require(try await store.artworkRevision())
    #expect(fourth != third)
    // A full resync moves it when covers differ (the artist is gone), but
    // not when it repeats the same covers.
    var song = Track(id: "t", title: "Song", artist: "A")
    try await store.replace(LibrarySnapshot(revision: "seven", tracks: [song]))
    let fifth = try #require(try await store.artworkRevision())
    #expect(fifth != fourth)
    try await store.replace(LibrarySnapshot(revision: "eight", tracks: [song]))
    #expect(try await store.artworkRevision() == fifth)
    song.coverSha = "ccc"
    try await store.replace(LibrarySnapshot(revision: "nine", tracks: [song]))
    #expect(try await store.artworkRevision() != fifth)
  }
}
