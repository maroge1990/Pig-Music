import Foundation
import Observation
import PigDomain

@available(macOS 14, *)
@MainActor @Observable public final class DownloadController {
  public private(set) var records: [DownloadRecord] = []
  public private(set) var progress: [String: Double] = [:]
  public private(set) var running = false
  public var budgetBytes: Int64 = 5 * 1024 * 1024 * 1024
  public let archive: DownloadArchive
  @ObservationIgnored private let source: any DeviceCopySource
  @ObservationIgnored private let onFailure: @MainActor (any Error) -> Void
  @ObservationIgnored private var worker: Task<Void, Never>?
  @ObservationIgnored private var generation = 0
  public init(
    archive: DownloadArchive, source: any DeviceCopySource,
    onFailure: @escaping @MainActor (any Error) -> Void = { _ in }
  ) {
    self.archive = archive
    self.source = source
    self.onFailure = onFailure
  }
  public func reload() async { records = await archive.snapshot() }
  public func enqueue(_ tracks: [Track], quality: String = "original") async throws {
    try await archive.enqueue(tracks, quality: quality)
    await reload()
    resume()
  }
  public func resume() {
    guard worker == nil else { return }
    let stamp = generation
    running = true
    worker = Task {
      defer {
        if generation == stamp {
          worker = nil
          running = false
        }
      }
      while !Task.isCancelled, generation == stamp {
        let all = await archive.snapshot()
        guard let record = all.first(where: { $0.state == "queued" }) else { break }
        do {
          var manifest = try await source.deviceCopy(
            trackId: record.id, quality: record.quality, create: true)
          var polls = 0
          while ["queued", "preparing"].contains(manifest.state) {
            try Task.checkCancellation()
            guard generation == stamp else { throw CancellationError() }
            polls += 1
            guard polls < 300 else { throw OfflineFailure.unsafeResponse }
            try await Task.sleep(for: .seconds(2))
            manifest = try await source.deviceCopy(
              trackId: record.id, quality: record.quality, create: false)
          }
          let request = try await source.copyRequest(trackId: record.id, quality: record.quality)
          try await archive.transfer(
            record, manifest: manifest, request: request, budget: budgetBytes
          ) { [weak self] bytes, total in
            await self?.updateProgress(id: record.id, bytes: bytes, total: total, stamp: stamp)
          }
        } catch is CancellationError { break } catch {
          guard generation == stamp else { break }
          try? await archive.fail(id: record.id, message: error.localizedDescription)
          onFailure(error)
          if case OfflineFailure.authentication = error { break }
        }
        guard generation == stamp else { break }
        await reload()
      }
    }
  }
  private func updateProgress(id: String, bytes: Int64, total: Int64, stamp: Int) async {
    if generation == stamp {
      progress[id] = total > 0 ? Double(bytes) / Double(total) : 0
      let snapshot = await archive.snapshot()
      if generation == stamp { records = snapshot }
    }
  }
  public func remove(id: String) async {
    await pause()
    try? await archive.remove(id: id)
    await reload()
    progress[id] = nil
    resume()
  }
  public func pause() async {
    generation += 1
    let previous = worker
    previous?.cancel()
    await previous?.value
    worker = nil
    running = false
    try? await archive.interruptRunning()
    await reload()
  }
  public func reconcile(_ allowed: [String: String?]) async {
    await pause()
    try? await archive.reconcile(allowed)
    await reload()
  }
  public func clear() async {
    await pause()
    try? await archive.clear()
    await reload()
    progress = [:]
  }
}
