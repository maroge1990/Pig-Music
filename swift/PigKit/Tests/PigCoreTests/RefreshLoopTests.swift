import PigDomain
import Testing

/// A server, the phone's copy, and a refresh shaped like `AppModel.refresh`:
/// read the library delta, then await the slower follow-up work (preferences,
/// Watch, requests). The test holds that follow-up open while a live revision
/// event arrives.
@MainActor private final class Phone {
  var server = 1
  var local = 0
  var deltaReads: [Int] = []
  private var gate: CheckedContinuation<Void, Never>?
  private var reachedFollowUp: CheckedContinuation<Void, Never>?
  var holdNextFollowUp = false

  func refreshBody() async {
    local = server
    deltaReads.append(server)
    if holdNextFollowUp {
      holdNextFollowUp = false
      reachedFollowUp?.resume()
      reachedFollowUp = nil
      await withCheckedContinuation { gate = $0 }
    }
  }
  func waitForFollowUp() async {
    await withCheckedContinuation { reachedFollowUp = $0 }
  }
  func releaseFollowUp() {
    gate?.resume()
    gate = nil
  }
}

/// `AppModel.refresh` before the fix: a refresh already running drops the call.
@MainActor private final class OldGuard {
  var syncing = false
  func refresh(_ phone: Phone) async {
    guard !syncing else { return }
    syncing = true
    defer { syncing = false }
    await phone.refreshBody()
  }
}

@MainActor struct RefreshLoopTests {
  /// The bug as it was: `guard !syncing` drops the event's refresh, and the
  /// manual refresh's delta was read before the change.
  @Test func theOldGuardDropsARevisionDuringAManualRefresh() async {
    let phone = Phone()
    let old = OldGuard()
    phone.holdNextFollowUp = true
    let manual = Task { @MainActor in await old.refresh(phone) }
    await phone.waitForFollowUp()
    phone.server = 2  // Another device changed the library.
    await old.refresh(phone)  // The live revision event.
    phone.releaseFollowUp()
    await manual.value
    #expect(phone.local == 1)  // Stale until some later refresh.
    #expect(phone.deltaReads == [1])
  }

  @Test func aRevisionDuringAManualRefreshIsReadAfterIt() async {
    let phone = Phone()
    let loop = RefreshLoop()
    phone.holdNextFollowUp = true
    let manual = Task { @MainActor in await loop.run { await phone.refreshBody() } }
    await phone.waitForFollowUp()
    phone.server = 2
    await loop.run { await phone.refreshBody() }  // Returns at once: remembered.
    #expect(loop.isRunning)
    phone.releaseFollowUp()
    await manual.value
    #expect(phone.deltaReads == [1, 2])
    #expect(phone.local == 2)
    #expect(!loop.isRunning)
  }

  @Test func severalRequestsDuringOneRefreshRunOnceMore() async {
    let phone = Phone()
    let loop = RefreshLoop()
    phone.holdNextFollowUp = true
    let manual = Task { @MainActor in await loop.run { await phone.refreshBody() } }
    await phone.waitForFollowUp()
    phone.server = 3
    for _ in 0..<3 { await loop.run { await phone.refreshBody() } }
    phone.releaseFollowUp()
    await manual.value
    #expect(phone.deltaReads == [1, 3])
  }

  /// Signing out or switching account during a refresh: the old account's
  /// refresh never repeats, and a new one starts straight away.
  @Test func anAccountChangeForgetsThePendingRefresh() async {
    let phone = Phone()
    let loop = RefreshLoop()
    phone.holdNextFollowUp = true
    let manual = Task { @MainActor in await loop.run { await phone.refreshBody() } }
    await phone.waitForFollowUp()
    await loop.run { await phone.refreshBody() }  // Remembered...
    loop.reset()  // ...then the account changes.
    var newAccountRan = false
    await loop.run { newAccountRan = true }
    #expect(newAccountRan)
    phone.releaseFollowUp()
    await manual.value
    #expect(phone.deltaReads == [1])
    #expect(!loop.isRunning)
  }

  @Test func aCancelledRefreshDoesNotRepeat() async {
    let loop = RefreshLoop()
    var runs = 0
    let task = Task { @MainActor in
      await loop.run {
        runs += 1
        withUnsafeCurrentTask { $0?.cancel() }
        await loop.run {}  // A request arrives, but this refresh was cancelled.
      }
    }
    await task.value
    #expect(runs == 1)
    #expect(!loop.isRunning)
  }
}
