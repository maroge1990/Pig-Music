import Foundation

/// Where the queue's next preparation starts. A restored queue shows where you
/// were and fetches nothing until Play (`waiting`); Next and Previous choose
/// their song first, so only that song is prepared. A saved position belongs
/// to one occurrence: it never carries over to a song chosen after it, however
/// long the preparation it was taken by takes.
public struct QueueStart: Sendable {
  /// A restored queue waiting for Play: nothing is fetched yet.
  public private(set) var waiting = false
  private var pending: (occurrence: UUID, seconds: Double)?
  public init() {}

  /// A queue starting at its current song, `seconds` in; a restored one may
  /// wait for Play.
  public mutating func restore(_ queue: PlaybackQueue, at seconds: Double, waiting: Bool) {
    self.waiting = waiting
    pending = nil
    seek(queue, to: seconds)
  }
  /// The position `occurrence` starts from: 0 for any other song.
  public func seconds(for occurrence: PlaybackOccurrence?) -> Double {
    guard let pending, pending.occurrence == occurrence?.id else { return 0 }
    return pending.seconds
  }
  /// The current song will start `seconds` in.
  public mutating func seek(_ queue: PlaybackQueue, to seconds: Double) {
    guard let current = queue.current, seconds.isFinite, seconds > 0 else {
      pending = nil
      return
    }
    pending = (current.id, seconds)
  }
  /// The start of `occurrence`, handed to its preparation. Every preparation
  /// takes one, so a saved position is used at most once and only by its song.
  public mutating func take(for occurrence: PlaybackOccurrence?) -> Double {
    defer { pending = nil }
    return seconds(for: occurrence)
  }
  /// Play (or Next or Previous) ends the wait. False when there was none.
  public mutating func begin() -> Bool {
    guard waiting else { return false }
    waiting = false
    return true
  }
  /// Next while waiting: moves `queue` to the song to prepare, from its start.
  /// False at the end of the queue, which is left as it was.
  public mutating func next(_ queue: inout PlaybackQueue, repeatMode: PlaybackRepeat) -> Bool {
    if !queue.next() {
      guard repeatMode == .all, !queue.items.isEmpty else { return false }
      queue.select(index: 0)
      for index in queue.items.indices { queue.renewOccurrence(at: index, id: UUID()) }
    }
    pending = nil
    return true
  }
  /// Previous while waiting: the saved position decides, as it would have
  /// playing, between restarting the song and going back one; from its start.
  public mutating func previous(_ queue: inout PlaybackQueue) {
    _ = queue.previous(elapsed: seconds(for: queue.current))
    pending = nil
  }
  public mutating func reset() { self = QueueStart() }
}
