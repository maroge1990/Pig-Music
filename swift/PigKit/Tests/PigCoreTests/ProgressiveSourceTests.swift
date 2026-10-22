import AVFoundation
import Foundation
import Testing

@testable import PigPlayback

/// A media server that honours Range requests and sends its body slowly.
private final class SlowMedia: @unchecked Sendable {
  static let shared = SlowMedia()
  private let lock = NSLock()
  private var data = Data()
  private var type = "audio/mpeg"
  private var chunk = 32768
  private var pause: TimeInterval = 0.01
  /// Bytes sent before the server stops answering (nil: no stall).
  private var stallAfter: Int?
  /// Requests starting here or later run past the range, then stall.
  private var oversendFrom: Int?
  private var ranges: [String] = []
  /// Ranges of requests the client cancelled before they finished.
  private var cancelled: [String] = []
  func set(
    _ data: Data, type: String = "audio/mpeg", chunk: Int = 32768, pause: TimeInterval = 0.01,
    stallAfter: Int? = nil, oversendFrom: Int? = nil
  ) {
    lock.withLock {
      self.data = data
      self.type = type
      self.chunk = chunk
      self.pause = pause
      self.stallAfter = stallAfter
      self.oversendFrom = oversendFrom
      ranges = []
      cancelled = []
    }
  }
  func requested() -> [String] { lock.withLock { ranges } }
  func cancelledRequests() -> [String] { lock.withLock { cancelled } }
  fileprivate func requestCancelled(_ range: String) { lock.withLock { cancelled.append(range) } }
  fileprivate func plan(_ range: String?) -> (
    Data, Int, Int, String, Int, TimeInterval, Int?, Bool
  ) {
    lock.withLock {
      ranges.append(range ?? "")
      var start = 0
      var end = data.count - 1
      if let range, let match = range.wholeMatch(of: /bytes=(\d+)-(\d*)/) {
        start = Int(match.1)!
        if let last = Int(match.2) { end = min(last, data.count - 1) }
      }
      let oversend = oversendFrom.map { start >= $0 } ?? false
      return (data, start, end, type, chunk, pause, oversend ? nil : stallAfter, oversend)
    }
  }
}

private final class SlowProtocol: URLProtocol, @unchecked Sendable {
  private let stopped = ReadStop()
  private let finished = ReadStop()
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    let ranged = request.value(forHTTPHeaderField: "Range")
    let (data, start, end, type, chunk, pause, stallAfter, oversend) = SlowMedia.shared.plan(
      ranged)
    let headers = [
      "Content-Type": type, "Content-Length": String(end - start + 1),
      "Content-Range": "bytes \(start)-\(end)/\(data.count)",
    ]
    client?.urlProtocol(
      self,
      didReceive: HTTPURLResponse(
        url: request.url!, statusCode: 206, httpVersion: "HTTP/1.1", headerFields: headers)!,
      cacheStoragePolicy: .notAllowed)
    let body = data.subdata(in: start..<end + 1) + Data(count: oversend ? 4 * chunk : 0)
    DispatchQueue.global().async { [self] in
      var offset = 0
      while offset < body.count {
        if stopped.stopped { return }
        if let stallAfter, start + offset >= stallAfter { return }
        let next = min(offset + chunk, body.count)
        client?.urlProtocol(self, didLoad: body.subdata(in: offset..<next))
        offset = next
        Thread.sleep(forTimeInterval: pause)
      }
      if oversend { return }
      finished.stop()
      client?.urlProtocolDidFinishLoading(self)
    }
  }
  override func stopLoading() {
    stopped.stop()
    if !finished.stopped {
      SlowMedia.shared.requestCancelled(request.value(forHTTPHeaderField: "Range") ?? "")
    }
  }
}

@Suite(.serialized) struct ProgressiveSourceTests {
  let url = URL(string: "https://media.invalid/song.mp3?signature=synthetic")!
  private func preparer(_ root: URL, maximum: Int = 64 * 1024 * 1024) throws
    -> AudioSourcePreparer
  {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [SlowProtocol.self]
    return try AudioSourcePreparer(
      root: root, maximumFileBytes: maximum, maximumTotalBytes: 128 * 1024 * 1024,
      configuration: configuration)
  }
  private func directory() throws -> URL {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    return root
  }
  private func read(
    _ bytes: any AudioBytes, at offset: Int, count: Int, stop: ReadStop = ReadStop()
  )
    async throws -> Data
  {
    try await Task.detached {
      var data = Data(count: count)
      let read = try data.withUnsafeMutableBytes {
        try bytes.read(offset: offset, count: count, into: $0.baseAddress!, stop: stop)
      }
      return data.prefix(read)
    }.value
  }

  @Test func playsBeforeTheFileArrivesAndFetchesWhereTheDecoderReads() async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    let data = Data((0..<4_000_000).map { UInt8(truncatingIfNeeded: $0 &* 31) })
    // About 2.5 s for the whole file at this pace.
    SlowMedia.shared.set(data, chunk: 32768, pause: 0.02)
    let owner = try preparer(root)
    let source = try await owner.prepare { url }
    let download = try #require(source.bytes as? ProgressiveDownload)
    // Ready while the body is still arriving (not a wall-clock bound: shared
    // CI runners took nearly 2 s to answer a stubbed request under load).
    #expect(download.phase == .loading)
    #expect(source.byteCount == data.count)
    // The opening is here almost at once.
    #expect(try await read(download, at: 0, count: 4096) == data.prefix(4096))
    // A read near the end (a seek, or an index stored there) jumps the transfer.
    let far = 3_500_000
    #expect(try await read(download, at: far, count: 8192) == data.subdata(in: far..<far + 8192))
    #expect(SlowMedia.shared.requested().contains { $0.hasPrefix("bytes=") && $0 != "bytes=0-" })
    #expect(try await readAll(source) == data)
    #expect(download.phase == .complete)
    await owner.release(source)
    #expect(!FileManager.default.fileExists(atPath: source.file.path))
  }

  @Test func aStoppedReaderStopsWaitingAtOnce() async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    SlowMedia.shared.set(Data(repeating: 3, count: 1_000_000), stallAfter: 65536)
    let owner = try preparer(root)
    let source = try await owner.prepare { url }
    let bytes = try source.audioBytes()
    let stop = ReadStop()
    let waiting = Task { try await read(bytes, at: 900_000, count: 1024, stop: stop) }
    try await Task.sleep(for: .milliseconds(200))
    let stopped = ContinuousClock.now
    stop.stop()
    bytes.wake()
    await #expect(throws: CancellationError.self) { try await waiting.value }
    #expect(ContinuousClock.now - stopped < .seconds(1))
    await owner.release(source)
  }

  @Test func decodingWhileArrivingMatchesTheCompleteFile() async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    // AAC in MP4 keeps its index at the end of the file: it must be fetched
    // before the start can decode.
    let fixture = root.appendingPathComponent("fixture.m4a")
    let format = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)!
    do {
      let file = try AVAudioFile(
        forWriting: fixture,
        settings: [
          AVFormatIDKey: kAudioFormatMPEG4AAC, AVSampleRateKey: 44100,
          AVNumberOfChannelsKey: 2, AVEncoderBitRateKey: 128000,
        ])
      let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 44100)!
      pcm.frameLength = 44100
      for second in 0..<6 {
        for channel in 0..<2 {
          for frame in 0..<44100 {
            pcm.floatChannelData![channel][frame] =
              0.3 * sin(Float(second * 44100 + frame) * 2 * .pi * 440 / 44100)
          }
        }
        try file.write(from: pcm)
      }
    }
    let encoded = try Data(contentsOf: fixture)
    SlowMedia.shared.set(encoded, type: "audio/mp4", chunk: 8192, pause: 0.005)
    let owner = try preparer(root)
    let source = try await owner.prepare {
      URL(string: "https://media.invalid/song.m4a?signature=synthetic")!
    }
    let output = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 2)!
    func decodeAll(_ bytes: any AudioBytes) async throws -> [Float] {
      let decoder = try await StreamingPCMDecoder.open(
        bytes, typeHint: kAudioFileM4AType, format: output)
      var samples: [Float] = []
      while let block = try await decoder.read(maxFrames: 4096) {
        samples.append(
          contentsOf: UnsafeBufferPointer(
            start: block.floatChannelData![0], count: Int(block.frameLength)))
      }
      return samples
    }
    let arriving = try await decodeAll(try source.audioBytes())
    let local = try await decodeAll(try LocalAudioBytes(file: fixture))
    #expect(arriving.count > 48000 * 5)
    #expect(arriving == local)
    await owner.release(source)
  }

  private static let ffmpeg = [
    "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
  ]
  .first { FileManager.default.isExecutableFile(atPath: $0) }

  /// Real FLAC and MP3 decode while arriving exactly as AVAudioFile decodes the
  /// complete file: every sample, and the same gapless length.
  @Test(.enabled(if: ffmpeg != nil), arguments: [("flac", "audio/flac"), ("mp3", "audio/mpeg")])
  func realFormatsMatchTheCompleteFileDecoder(_ format: (String, String)) async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    let fixture = root.appendingPathComponent("fixture." + format.0)
    let encode = Process()
    encode.executableURL = URL(fileURLWithPath: Self.ffmpeg!)
    encode.arguments =
      [
        "-v", "error", "-f", "lavfi", "-i", "anoisesrc=d=12:c=pink:a=0.3", "-ac", "2", "-ar",
        "44100",
      ]
      + (format.0 == "mp3" ? ["-c:a", "libmp3lame", "-b:a", "256k"] : ["-c:a", "flac"])
      + [fixture.path]
    try encode.run()
    encode.waitUntilExit()
    #expect(encode.terminationStatus == 0)
    SlowMedia.shared.set(try Data(contentsOf: fixture), type: format.1, chunk: 16384, pause: 0.002)
    let owner = try preparer(root)
    let source = try await owner.prepare {
      URL(string: "https://media.invalid/song.\(format.0)?signature=synthetic")!
    }
    let output = AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 2)!
    let streaming = try await StreamingPCMDecoder.open(source, format: output)
    var arriving: [Float] = []
    while let block = try await streaming.read(maxFrames: 2048) {
      arriving.append(
        contentsOf: UnsafeBufferPointer(
          start: block.floatChannelData![1], count: Int(block.frameLength)))
    }
    let complete = try PCMFileDecoder(url: fixture, format: output)
    var local: [Float] = []
    while let block = try complete.read(maxFrames: 2048) {
      local.append(
        contentsOf: UnsafeBufferPointer(
          start: block.floatChannelData![1], count: Int(block.frameLength)))
    }
    #expect(streaming.expectedFrames == complete.expectedFrames)
    #expect(arriving.count == local.count && arriving.count > 48000 * 11)
    #expect(arriving == local)
    await owner.release(source)
  }

  @Test func aSeekStartsDecodingPartWayWithoutTheWholeFile() async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    // Ten seconds of 16-bit WAV: 1.7 MB.
    let fixture = root.appendingPathComponent("fixture.wav")
    let format = AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)!
    do {
      let file = try AVAudioFile(
        forWriting: fixture,
        settings: [
          AVFormatIDKey: kAudioFormatLinearPCM, AVSampleRateKey: 44100,
          AVNumberOfChannelsKey: 2, AVLinearPCMBitDepthKey: 16,
        ])
      let pcm = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 44100)!
      pcm.frameLength = 44100
      for second in 0..<10 {
        for channel in 0..<2 {
          pcm.floatChannelData![channel].update(repeating: Float(second) / 20, count: 44100)
        }
        try file.write(from: pcm)
      }
    }
    // Slow enough that the end would take seconds to arrive in order.
    SlowMedia.shared.set(
      try Data(contentsOf: fixture), type: "audio/wav", chunk: 16384, pause: 0.05)
    let owner = try preparer(root)
    let source = try await owner.prepare {
      URL(string: "https://media.invalid/song.wav?signature=synthetic")!
    }
    let started = ContinuousClock.now
    let decoder = try await StreamingPCMDecoder.open(
      try source.audioBytes(), typeHint: kAudioFileWAVEType,
      format: AVAudioFormat(standardFormatWithSampleRate: 44100, channels: 2)!, startSeconds: 8.5)
    let block = try #require(try await decoder.read(maxFrames: 1024))
    #expect(ContinuousClock.now - started < .seconds(2))
    #expect(abs(block.floatChannelData![0][512] - 8 / 20) < 0.001)
    await owner.release(source)
  }

  private func waitForCancelledRequest(_ prefix: String = "bytes=") async throws -> Bool {
    func found() -> Bool { SlowMedia.shared.cancelledRequests().contains { $0.hasPrefix(prefix) } }
    for _ in 0..<40 where !found() { try await Task.sleep(for: .milliseconds(50)) }
    return found()
  }

  @Test func releasingASourceCancelsItsStalledTransfer() async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    // Headers and the opening, then the server stops sending.
    SlowMedia.shared.set(Data(repeating: 5, count: 1_000_000), stallAfter: 65536)
    let owner = try preparer(root)
    let source = try await owner.prepare { url }
    try await Task.sleep(for: .milliseconds(200))
    #expect(SlowMedia.shared.cancelledRequests().isEmpty)
    await owner.release(source)
    // The HTTP request itself is cancelled, not just the task reading it.
    #expect(try await waitForCancelledRequest())
  }

  @Test func aTransferThatFailsIsCancelledNotLeftOpen() async throws {
    let root = try directory()
    defer { try? FileManager.default.removeItem(at: root) }
    // A seek near the end makes the transfer jump there; that ranged answer
    // runs past the end of the file (a broken server), then stalls.
    SlowMedia.shared.set(
      Data(repeating: 6, count: 4_000_000), chunk: 16384, pause: 0.05, oversendFrom: 2_000_000)
    let owner = try preparer(root)
    let source = try await owner.prepare { url }
    let bytes = try source.audioBytes()
    _ = try await read(bytes, at: 3_990_000, count: 1024)
    #expect(SlowMedia.shared.requested().contains("bytes=3990000-3999999"))
    #expect(try await waitForCancelledRequest("bytes=3990000-"))
    await owner.release(source)
  }
}
