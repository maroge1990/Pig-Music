import Foundation
import PigDomain
import PigStore
import Testing

struct MutationOutboxTests {
  @Test func durableOrderingAndConflictsStayWithinAccountDatabase() async throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let path = root.appendingPathComponent("person-one.sqlite").path
    let first = OfflineMutation(action: "create", name: "Queued playlist")
    let second = OfflineMutation(
      action: "append", playlistId: first.id,
      track: Track(id: "song", title: "Song", artist: "Artist"))
    let store = try LibraryStore(path: path)
    try await store.enqueueMutation(first)
    try await store.enqueueMutation(first)
    try await store.enqueueMutation(second)
    let restored = try LibraryStore(path: path)
    #expect(try await restored.pendingMutations().map(\.id) == [first.id, second.id])
    var pending = try #require(await restored.pendingMutations().first)
    pending.state = "conflict"
    pending.message = "Review current playlist"
    try await restored.updateMutation(pending)
    #expect(try await store.pendingMutations().first?.state == "conflict")
    let other = try LibraryStore(path: root.appendingPathComponent("person-two.sqlite").path)
    #expect(try await other.pendingMutations().isEmpty)
    try await restored.acknowledgeMutation(first.id)
    #expect(try await store.pendingMutations().map(\.id) == [second.id])
  }
}
