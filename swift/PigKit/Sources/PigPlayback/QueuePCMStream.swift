import AVFoundation
import Foundation
import PigDomain

public struct QueueAudioMarker: Sendable, Equatable {
  public let index: Int
  /// The incoming occurrence becomes the principal metadata at the fade midpoint.
  public let switchFrame: Int64
  public let originFrame: Int64
  public let durationFrames: Int64
  public var occurrenceID: UUID? = nil
}
public struct QueuePCMBlock: Sendable {
  public let pcm: PCMBlock
  public let markers: [QueueAudioMarker]
}

/// A bounded local decoder queue. Sources are prefetched one occurrence ahead;
/// complete-file preparation can still stall a transition when the network is slow.
public actor QueuePCMStream {
  public typealias Acquire = @Sendable (PlaybackOccurrence) async throws -> PreparedAudioSource
  public typealias Release = @Sendable (PreparedAudioSource) async -> Void
  private let items: [PlaybackOccurrence]
  private let acquire: Acquire
  private let release: Release
  private let format: AVAudioFormat
  private let rate: Double
  private let blockFrames: Int
  private let repeatMode: PlaybackRepeat
  private var cycle = 0
  private var upcomingOccurrence: PlaybackOccurrence?
  private let crossfade: Bool
  private let fadeSeconds: Double
  private var index: Int
  private var lease: PreparedAudioSource?
  private var decoder: PCMFileDecoder?
  private var upcoming: Task<PreparedAudioSource, Error>?
  private var incomingLease: PreparedAudioSource?
  private var incomingDecoder: PCMFileDecoder?
  private var tail: FrameRing
  private var head: FrameRing
  private var holdFrames = 0
  private var ended = false
  private var transitionReady = false
  private var prefix = 0
  private var overlap = 0
  private var mixed = 0
  private var outputFrames: Int64 = 0
  private var pendingMarkers: [QueueAudioMarker] = []
  private var closed = false
  private var reading = false
  private var sourceFailure: Error?

  public init(
    items: [PlaybackOccurrence], startingAt: Int = 0, startSeconds: Double = 0,
    crossfade: Bool = false, fadeSeconds: Double = 3, repeatMode: PlaybackRepeat = .off,
    sampleRate: Double = 48000,
    blockFrames: Int = 2048, acquire: @escaping Acquire, release: @escaping Release
  ) async throws {
    guard items.indices.contains(startingAt), startSeconds.isFinite, startSeconds >= 0,
      fadeSeconds.isFinite, (0...12).contains(fadeSeconds),
      [44100.0, 48000.0, 96000.0].contains(sampleRate), (256...8192).contains(blockFrames),
      let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: 2)
    else { throw AudioPipelineFailure.invalidConfiguration }
    self.items = items
    self.index = startingAt
    self.acquire = acquire
    self.release = release
    self.format = format
    rate = sampleRate
    self.blockFrames = blockFrames
    self.repeatMode = repeatMode
    self.crossfade = crossfade
    self.fadeSeconds = fadeSeconds
    tail = FrameRing(capacity: Int(fadeSeconds * sampleRate) + blockFrames)
    head = FrameRing(capacity: max(1, Int(fadeSeconds * sampleRate)))
    let source = try await acquire(items[startingAt])
    do {
      try Task.checkCancellation()
      let first = try PCMFileDecoder(url: source.file, format: format, startSeconds: startSeconds)
      decoder = first
      lease = source
      let skipped = min(
        first.expectedFrames,
        Int64(min(startSeconds * rate, Double(first.expectedFrames)).rounded()))
      pendingMarkers = [
        QueueAudioMarker(
          index: index, switchFrame: 0, originFrame: -skipped,
          durationFrames: first.expectedFrames, occurrenceID: items[index].id)
      ]
      configureUpcoming()
    } catch {
      await release(source)
      throw error
    }
  }

  private var nextIndex: Int? {
    if repeatMode == .one { return index }
    if index + 1 < items.count { return index + 1 }
    return repeatMode == .all ? 0 : nil
  }
  private func configureUpcoming() {
    holdFrames = 0
    guard let nextIndex else {
      upcomingOccurrence = nil
      return
    }
    let incoming = items[nextIndex]
    let repeated = cycle > 0 || nextIndex <= index
    let next = repeated ? PlaybackOccurrence(track: incoming.track) : incoming
    upcomingOccurrence = next
    let mode = TransitionPlanner.mode(
      crossfade: crossfade && repeatMode != .one,
      albumOrder: TransitionPlanner.albumOrder(outgoing: items[index].track, incoming: next.track),
      duration: fadeSeconds)
    if case .crossfade(let seconds) = mode { holdFrames = Int(seconds * rate) }
    let acquire = acquire
    upcoming = Task { try await acquire(next) }
  }

  public func next() async throws -> QueuePCMBlock? {
    guard !closed else { throw CancellationError() }
    guard !reading else { throw AudioSourceFailure.busy }
    reading = true
    defer { reading = false }
    while true {
      try Task.checkCancellation()
      guard !closed else { throw CancellationError() }
      while !ended {
        if tail.count > holdFrames {
          return emit(tail.pop(min(blockFrames, tail.count - holdFrames)))
        }
        if let decoded = try decoder?.read(maxFrames: blockFrames) {
          tail.push(decoded)
        } else {
          ended = true
        }
      }
      guard let followingIndex = nextIndex else {
        if tail.count > 0 { return emit(tail.pop(min(blockFrames, tail.count))) }
        return nil
      }
      if let sourceFailure {
        if tail.count > 0 { return emit(tail.pop(min(blockFrames, tail.count))) }
        throw sourceFailure
      }
      if !transitionReady {
        guard let upcoming else { throw AudioPipelineFailure.stalled }
        let source: PreparedAudioSource
        do {
          source = try await withTaskCancellationHandler {
            try await upcoming.value
          } onCancel: {
            upcoming.cancel()
          }
        } catch {
          try Task.checkCancellation()
          sourceFailure = error
          continue
        }
        // close() also awaits this task; ownership remains here only while the stream is open.
        guard !closed else { throw CancellationError() }
        self.upcoming = nil
        incomingLease = source
        try Task.checkCancellation()
        let next: PCMFileDecoder
        do { next = try PCMFileDecoder(url: source.file, format: format) } catch {
          sourceFailure = error
          continue
        }
        incomingDecoder = next
        do {
          while head.count < min(holdFrames, tail.count) {
            try Task.checkCancellation()
            guard
              let decoded = try next.read(
                maxFrames: min(blockFrames, min(holdFrames, tail.count) - head.count))
            else { break }
            head.push(decoded)
          }
        } catch {
          try Task.checkCancellation()
          sourceFailure = error
          continue
        }
        overlap = min(tail.count, head.count)
        prefix = tail.count - overlap
        let origin = outputFrames + Int64(prefix)
        pendingMarkers.append(
          QueueAudioMarker(
            index: followingIndex,
            switchFrame: origin + Int64(overlap / 2), originFrame: origin,
            durationFrames: next.expectedFrames, occurrenceID: upcomingOccurrence?.id))
        transitionReady = true
      }
      if prefix > 0 {
        let count = min(blockFrames, prefix)
        prefix -= count
        return emit(tail.pop(count))
      }
      if mixed < overlap {
        let count = min(blockFrames, overlap - mixed)
        var outgoing = tail.pop(count)
        let incoming = head.pop(count)
        for frame in 0..<count {
          let progress = overlap == 1 ? 0.5 : Double(mixed + frame) / Double(overlap - 1)
          let gains = TransitionPlanner.gains(progress: progress)
          for channel in 0..<2 {
            outgoing[channel][frame] =
              outgoing[channel][frame] * gains.outgoing + incoming[channel][frame] * gains.incoming
          }
        }
        mixed += count
        return emit(outgoing)
      }
      let old = lease
      lease = incomingLease
      decoder = incomingDecoder
      incomingLease = nil
      incomingDecoder = nil
      if followingIndex <= index { cycle += 1 }
      index = followingIndex
      ended = false
      transitionReady = false
      prefix = 0
      overlap = 0
      mixed = 0
      // Release outgoing encoded storage before reserving the following source.
      if let old { await release(old) }
      guard !closed else { throw CancellationError() }
      configureUpcoming()
    }
  }
  private func emit(_ channels: [[Float]]) -> QueuePCMBlock {
    let markers = pendingMarkers
    pendingMarkers.removeAll()
    outputFrames += Int64(channels[0].count)
    return QueuePCMBlock(pcm: PCMBlock(sampleRate: rate, channels: channels), markers: markers)
  }

  /// The owner cancels/awaits its pump before closing, so no decoder is still in use.
  public func close() async {
    guard !closed else { return }
    closed = true
    let pending = upcoming
    upcoming = nil
    pending?.cancel()
    decoder = nil
    incomingDecoder = nil
    if let lease {
      self.lease = nil
      await release(lease)
    }
    if let incomingLease {
      self.incomingLease = nil
      await release(incomingLease)
    }
    if let pending, let source = try? await pending.value { await release(source) }
  }
}
