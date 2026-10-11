import AVFoundation
import Foundation
import PigDomain

public enum QueuePlaybackState: Sendable, Equatable {
  case idle, preparing, buffering, playing, paused, ended, failed
}
public struct QueuePlaybackSnapshot: Sendable, Equatable {
  public var state: QueuePlaybackState = .idle
  public var index = 0
  public var occurrenceID: UUID?
  public var elapsed: Double = 0
  public var duration: Double = 0
  public var wantsPlayback = false
  public var error: String?
}

/// Injected output makes scheduling/lifecycle tests silent and deterministic.
@MainActor public protocol QueueAudioOutput: AnyObject {
  var positionFrames: Int64 { get }
  func configure(sampleRate: Double, blockFrames: Int) throws
  func schedule(_ block: PCMBlock, completion: @escaping @Sendable () -> Void) throws
  func resume()
  func pause()
  func stop()
}

/// Live output adapter; the app owner configures AVAudioSession and handles route/interruption events.
@MainActor public final class EngineQueueOutput: QueueAudioOutput {
  private let engine = AVAudioEngine()
  private let node = AVAudioPlayerNode()
  private var connected = false
  private var generation = 0
  private var scheduledFrames: Int64 = 0
  private var completedFrames: Int64 = 0
  private var segmentOrigin: Int64 = 0
  private var nodeOrigin: Int64 = 0
  private var pausedPosition: Int64 = 0
  public init() { engine.attach(node) }
  public var engineIdentity: ObjectIdentifier { ObjectIdentifier(engine) }
  public var requiresRecovery: Bool { connected && !engine.isRunning }
  private var nodePosition: Int64 {
    guard let time = node.lastRenderTime, let player = node.playerTime(forNodeTime: time) else {
      return 0
    }
    return max(0, player.sampleTime)
  }
  public var positionFrames: Int64 {
    guard node.isPlaying else { return pausedPosition }
    return min(
      scheduledFrames, max(completedFrames, segmentOrigin + max(0, nodePosition - nodeOrigin)))
  }
  public func configure(sampleRate: Double, blockFrames: Int) throws {
    stop()
    if connected { engine.disconnectNodeOutput(node) }
    guard let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 2) else {
      throw AudioPipelineFailure.invalidConfiguration
    }
    engine.connect(node, to: engine.mainMixerNode, format: format)
    connected = true
    engine.prepare()
    try engine.start()
  }
  public func schedule(_ block: PCMBlock, completion: @escaping @Sendable () -> Void) throws {
    if scheduledFrames == completedFrames, node.isPlaying {
      // Remove starvation silence from the music timeline when scheduling resumes.
      segmentOrigin = completedFrames
      nodeOrigin = nodePosition
    }
    let frames = Int64(block.frameCount)
    scheduledFrames += frames
    let stamp = generation
    node.scheduleBuffer(try block.audioBuffer(), completionCallbackType: .dataPlayedBack) {
      [weak self] _ in
      Task { @MainActor in
        guard let self, self.generation == stamp else { return }
        self.completedFrames += frames
        completion()
      }
    }
  }
  public func resume() { node.play() }
  public func pause() {
    pausedPosition = positionFrames
    node.pause()
  }
  public func stop() {
    generation += 1
    node.stop()
    engine.stop()
    scheduledFrames = 0
    completedFrames = 0
    segmentOrigin = 0
    nodeOrigin = 0
    pausedPosition = 0
  }

}

/// Realtime scheduling candidate, exposed only through the app’s opt-in testing setting.
@MainActor public final class RealtimeQueueSession {
  public private(set) var snapshot = QueuePlaybackSnapshot()
  public var onUpdate: (@MainActor (QueuePlaybackSnapshot) -> Void)?
  public private(set) var peakScheduledFrames: Int64 = 0
  private let output: any QueueAudioOutput
  private let rate: Double
  private let blockFrames: Int
  private var items: [PlaybackOccurrence] = []
  private var acquire: QueuePCMStream.Acquire?
  private var release: QueuePCMStream.Release?
  private var crossfade = false
  private var fadeSeconds: Double = 3
  private var pump: Task<Void, Never>?
  private var generation = 0
  private var pendingFrames: Int64 = 0
  private var timeline: [QueueAudioMarker] = []
  private var ready = false
  private var clock: Task<Void, Never>?
  private var sourceWaiting = false

  public init(output: any QueueAudioOutput, sampleRate: Double = 48000, blockFrames: Int = 2048)
    throws
  {
    guard [44100.0, 48000.0, 96000.0].contains(sampleRate), (256...8192).contains(blockFrames)
    else {
      throw AudioPipelineFailure.invalidConfiguration
    }
    self.output = output
    rate = sampleRate
    self.blockFrames = blockFrames
  }

  public func replace(
    _ items: [PlaybackOccurrence], startingAt: Int = 0, autoplay: Bool = true,
    crossfade: Bool = false, fadeSeconds: Double = 3,
    acquire: @escaping QueuePCMStream.Acquire, release: @escaping QueuePCMStream.Release
  ) {
    self.items = items
    self.acquire = acquire
    self.release = release
    self.crossfade = crossfade
    self.fadeSeconds = fadeSeconds
    guard !items.isEmpty else {
      stop()
      return
    }
    restart(index: min(max(0, startingAt), items.count - 1), seconds: 0, autoplay: autoplay)
  }

  /// Connects signed-server/provider resolution to temporary source leases.
  public func replace(
    _ items: [PlaybackOccurrence], startingAt: Int = 0, autoplay: Bool = true,
    crossfade: Bool = false, fadeSeconds: Double = 3, preparer: AudioSourcePreparer,
    resolve: @escaping @Sendable (Track) async throws -> URL
  ) {
    replace(
      items, startingAt: startingAt, autoplay: autoplay, crossfade: crossfade,
      fadeSeconds: fadeSeconds,
      acquire: { item in try await preparer.prepare { try await resolve(item.track) } },
      release: { source in await preparer.release(source) })
  }

  public func pause() {
    snapshot.wantsPlayback = false
    output.pause()
    if ready { snapshot.state = .paused }
    publish()
  }
  public func resume() {
    guard snapshot.state != .idle, snapshot.state != .ended, snapshot.state != .failed else {
      return
    }
    snapshot.wantsPlayback = true
    if ready {
      output.resume()
      snapshot.state = .playing
    }
    publish()
  }
  public func seek(_ seconds: Double) {
    guard !items.isEmpty, seconds.isFinite else { return }
    refreshPosition()
    restart(
      index: snapshot.index, seconds: min(max(0, seconds), snapshot.duration),
      autoplay: snapshot.wantsPlayback)
  }
  public func next() {
    refreshPosition()
    guard snapshot.index + 1 < items.count else {
      stop()
      return
    }
    restart(index: snapshot.index + 1, seconds: 0, autoplay: snapshot.wantsPlayback)
  }
  public func previous() {
    refreshPosition()
    let index = snapshot.elapsed > 3 ? snapshot.index : max(0, snapshot.index - 1)
    restart(index: index, seconds: 0, autoplay: snapshot.wantsPlayback)
  }
  @discardableResult public func stop() -> Task<Void, Never>? {
    generation += 1
    pump?.cancel()
    clock?.cancel()
    clock = nil
    output.stop()
    ready = false
    sourceWaiting = false
    pendingFrames = 0
    timeline = []
    snapshot = QueuePlaybackSnapshot()
    items = []
    acquire = nil
    release = nil
    publish()
    return pump
  }
  /// Waits for cancelled decoders and acquired/prefetched source leases to be released.
  public func stopAndWait() async {
    stop()
    let stamp = generation
    let stopped = pump
    await stopped?.value
    if generation == stamp { pump = nil }
  }

  private func restart(index: Int, seconds: Double, autoplay: Bool) {
    generation += 1
    let stamp = generation
    let old = pump
    old?.cancel()
    clock?.cancel()
    clock = nil
    output.stop()
    ready = false
    sourceWaiting = false
    pendingFrames = 0
    peakScheduledFrames = 0
    timeline = []
    snapshot = QueuePlaybackSnapshot(
      state: .preparing, index: index,
      occurrenceID: items[index].id, elapsed: seconds, duration: items[index].track.duration ?? 0,
      wantsPlayback: autoplay)
    publish()
    let items = items
    let crossfade = crossfade
    let fade = fadeSeconds
    guard let acquire, let release else { return }
    // Old cleanup completes before a new source reservation can race the same preparer.
    pump = Task { [weak self] in
      await old?.value
      guard let self, generation == stamp, !Task.isCancelled else { return }
      var stream: QueuePCMStream?
      do {
        let current = try await QueuePCMStream(
          items: items, startingAt: index, startSeconds: seconds,
          crossfade: crossfade, fadeSeconds: fade, sampleRate: rate, blockFrames: blockFrames,
          acquire: acquire, release: release)
        stream = current
        try Task.checkCancellation()
        guard generation == stamp else { throw CancellationError() }
        try output.configure(sampleRate: rate, blockFrames: blockFrames)
        var exhausted = false
        var sourceFailure: Error?
        startClock(generation: stamp)
        while !exhausted || pendingFrames > 0 {
          try Task.checkCancellation()
          guard generation == stamp else { throw CancellationError() }
          while !exhausted && pendingFrames <= Int64(blockFrames * 3) {
            let decoded: QueuePCMBlock?
            sourceWaiting = true
            do { decoded = try await current.next() } catch {
              sourceWaiting = false
              try Task.checkCancellation()
              sourceFailure = error
              exhausted = true
              break
            }
            sourceWaiting = false
            try Task.checkCancellation()
            guard generation == stamp else { throw CancellationError() }
            guard let block = decoded else {
              exhausted = true
              break
            }
            try Task.checkCancellation()
            guard generation == stamp else { throw CancellationError() }
            timeline.append(contentsOf: block.markers)
            let frames = Int64(block.pcm.frameCount)
            pendingFrames += frames
            peakScheduledFrames = max(peakScheduledFrames, pendingFrames)
            try output.schedule(block.pcm) { [weak self] in
              Task { @MainActor in
                guard let self, self.generation == stamp else { return }
                self.pendingFrames = max(0, self.pendingFrames - frames)
              }
            }
          }
          if !ready {
            ready = true
            if snapshot.wantsPlayback {
              output.resume()
              snapshot.state = .playing
            } else {
              snapshot.state = .paused
            }
            refreshPosition()
            publish()
          }
          if exhausted && pendingFrames == 0 { break }
          try await Task.sleep(for: .milliseconds(20))
        }
        try Task.checkCancellation()
        guard generation == stamp else { throw CancellationError() }
        refreshPosition()
        snapshot.state = sourceFailure == nil ? .ended : .failed
        snapshot.error = sourceFailure?.localizedDescription
        snapshot.wantsPlayback = false
        snapshot.elapsed = snapshot.duration
        output.pause()
        publish()
      } catch {
        if generation == stamp, !Task.isCancelled {
          output.stop()
          snapshot.state = .failed
          snapshot.wantsPlayback = false
          snapshot.error = error.localizedDescription
          publish()
        }
      }
      if generation == stamp {
        clock?.cancel()
        clock = nil
      }
      if let stream { await stream.close() }
    }
  }
  /// Rebuild after an interrupted/stopped engine or a route configuration change.
  public func recoverOutput() {
    guard ready, !items.isEmpty, snapshot.state != .ended, snapshot.state != .failed else { return }
    refreshPosition()
    restart(index: snapshot.index, seconds: snapshot.elapsed, autoplay: snapshot.wantsPlayback)
  }
  private func startClock(generation stamp: Int) {
    clock?.cancel()
    clock = Task { [weak self] in
      while !Task.isCancelled {
        guard let self, generation == stamp else { return }
        if ready {
          if snapshot.wantsPlayback, sourceWaiting, pendingFrames == 0 {
            snapshot.state = .buffering
          } else if snapshot.wantsPlayback, pendingFrames > 0 {
            snapshot.state = .playing
          }
          refreshPosition()
          publish()
        }
        do { try await Task.sleep(for: .milliseconds(100)) } catch { return }
      }
    }
  }
  private func refreshPosition() {
    guard ready else { return }
    let position = output.positionFrames
    guard let marker = timeline.last(where: { $0.switchFrame <= position }),
      items.indices.contains(marker.index)
    else { return }
    if let current = timeline.lastIndex(where: { $0.switchFrame <= position }), current > 0 {
      timeline.removeFirst(current)
    }
    snapshot.index = marker.index
    snapshot.occurrenceID = items[marker.index].id
    snapshot.duration = Double(marker.durationFrames) / rate
    snapshot.elapsed = min(snapshot.duration, max(0, Double(position - marker.originFrame) / rate))
  }
  private func publish() { onUpdate?(snapshot) }
}
