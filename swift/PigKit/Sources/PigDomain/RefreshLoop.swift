import Foundation

/// One library refresh at a time, without dropping requests.
///
/// A refresh asked for while another runs (a live revision event during a
/// manual pull-to-refresh, say) is remembered, and the running refresh goes
/// round once more when it finishes: the delta it already read cannot contain
/// that change. `reset()` (account change or sign-out) forgets everything, and
/// a refresh that began before it never repeats or touches the new state.
@MainActor public final class RefreshLoop {
  private var running = false
  private var pending = false
  private var epoch = 0
  public init() {}
  /// Whether a refresh is in progress.
  public var isRunning: Bool { running }
  /// Runs `work`, or, while a run is in progress, asks it to repeat.
  public func run(_ work: () async -> Void) async {
    guard !running else {
      pending = true
      return
    }
    running = true
    let mine = epoch
    repeat {
      pending = false
      await work()
    } while epoch == mine && pending && !Task.isCancelled
    if epoch == mine {
      running = false
      pending = false
    }
  }
  public func reset() {
    epoch += 1
    running = false
    pending = false
  }
}
