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
