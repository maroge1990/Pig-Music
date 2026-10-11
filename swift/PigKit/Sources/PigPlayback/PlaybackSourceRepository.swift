import Foundation
import PigDomain

/// Account-scoped, two-file temporary cache. Each decoder gets its own reference lease.
/// This is transient playback storage, not durable offline access.
public actor PlaybackSourceRepository {
  private struct Key: Hashable {
    let id: String
    let revision: String?
    let state: String?
    init(_ track: Track) {
      id = track.id
      revision = track.sourceRevision
      state = track.serverState
    }
  }
  private struct Entry {
    let source: PreparedAudioSource
    var references = 0
    var touched: UInt64 = 0
  }
  private let preparer: AudioSourcePreparer
  private var entries: [Key: Entry] = [:]
  private var references: [UUID: Key] = [:]
  private var clock: UInt64 = 0
  private var busy = false
  private var generation = 0
  public init(preparer: AudioSourcePreparer) { self.preparer = preparer }

  public func acquire(_ track: Track, resolve: @escaping @Sendable (Track) async throws -> URL)
    async throws -> PreparedAudioSource
  {
    try Task.checkCancellation()
    let key = Key(track)
    if entries[key] != nil { return lease(key) }
    guard !busy else { throw AudioSourceFailure.busy }
    busy = true
    defer { busy = false }
    let stamp = generation
    if entries.count >= 2 {
      guard
        let victim = entries.filter({ $0.value.references == 0 }).min(by: {
          $0.value.touched < $1.value.touched
        })
      else {
        throw AudioSourceFailure.storageLimit
      }
      entries.removeValue(forKey: victim.key)
      await preparer.release(victim.value.source)
    }
    guard generation == stamp else { throw CancellationError() }
    let source = try await preparer.prepare { try await resolve(track) }
    guard generation == stamp, !Task.isCancelled else {
      await preparer.release(source)
      throw CancellationError()
    }
    entries[key] = Entry(source: source)
    return lease(key)
  }
  /// Trusted local staging is deliberately separate from the remote resolver.
  public func acquireLocal(_ track: Track, file: URL) async throws -> PreparedAudioSource {
    let key = Key(track)
    try Task.checkCancellation()
    if entries[key] != nil { return lease(key) }
    guard !busy else { throw AudioSourceFailure.busy }
    busy = true
    defer { busy = false }
    let stamp = generation
    if entries.count >= 2 {
      guard
        let victim = entries.filter({ $0.value.references == 0 }).min(by: {
          $0.value.touched < $1.value.touched
        })
      else { throw AudioSourceFailure.storageLimit }
      entries.removeValue(forKey: victim.key)
      await preparer.release(victim.value.source)
    }
    guard generation == stamp else { throw CancellationError() }
    let source = try await preparer.stageLocalFile(file)
    guard generation == stamp, !Task.isCancelled else {
      await preparer.release(source)
      throw CancellationError()
    }
    entries[key] = Entry(source: source)
    return lease(key)
  }
  private func lease(_ key: Key) -> PreparedAudioSource {
    clock &+= 1
    var entry = entries[key]!
    entry.references += 1
    entry.touched = clock
    entries[key] = entry
    let id = UUID()
    references[id] = key
    return PreparedAudioSource(id: id, file: entry.source.file, byteCount: entry.source.byteCount)
  }
  public func release(_ source: PreparedAudioSource) {
    guard let key = references.removeValue(forKey: source.id), var entry = entries[key] else {
      return
    }
    entry.references = max(0, entry.references - 1)
    entries[key] = entry
  }
  public func savedRevisions() -> [String: String?] {
    var result: [String: String?] = [:]
    for key in entries.keys where key.state != "not_in_library" {
      result.updateValue(key.revision, forKey: key.id)
    }
    return result
  }
  /// Owner must stop and await decoders before clearing account/library access.
  public func reset() async {
    generation += 1
    references.removeAll()
    entries.removeAll()
    await preparer.reset()
  }
}
