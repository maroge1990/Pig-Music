import Foundation
import PigStore

public actor SyncCoordinator {
  private let source: any LibrarySource
  private let store: LibraryStore
  private var active = false
  public init(source: any LibrarySource, store: LibraryStore) {
    self.source = source
    self.store = store
  }
  public func refresh() async throws {
    guard !active else { return }
    active = true
    defer { active = false }
    if let revision = try await store.revision() {
      do {
        let delta = try await source.changes(since: revision)
        try Task.checkCancellation()
        try await store.apply(delta)
        return
      } catch NativeFailure.resync
      { /* expired history: preserve old data until replacement succeeds */  }
    }
    for attempt in 0..<3 {
      do {
        let snapshot = try await source.bootstrap()
        try Task.checkCancellation()
        try await store.replace(snapshot)
        return
      } catch NativeFailure.changed {
        if attempt == 2 { throw NativeFailure.changed }
      }
    }
  }
}
