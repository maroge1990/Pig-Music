import AVFoundation
import Foundation

@testable import PigPlayback

/// A local file whose bytes arrive when the test says. A read past them
/// waits (at most ten seconds, so a mistake fails rather than hangs), except
/// in the last 128 bytes, where Core Audio looks for an ID3v1 tag on opening
/// and a real transfer fetches them at once.
final class MeteredBytes: AudioBytes, @unchecked Sendable {
  private let file: LocalAudioBytes
  private let condition = NSCondition()
  private var allowed: Int
  private var readers = 0
  init(file: URL, allowed: Int) throws {
    self.file = try LocalAudioBytes(file: file)
    self.allowed = allowed
  }
  var length: Int { file.length }
  var waiting: Bool { condition.withLock { readers > 0 } }
  var complete: Bool { condition.withLock { allowed >= length } }
  func allow(_ count: Int) {
    condition.withLock {
      allowed = count
      condition.broadcast()
    }
  }
  func read(offset: Int, count: Int, into buffer: UnsafeMutableRawPointer, stop: ReadStop)
    throws -> Int
  {
    condition.lock()
    let deadline = Date(timeIntervalSinceNow: 10)
    while offset + min(count, length - offset) > allowed, offset < length - 128 {
      if stop.stopped || Date() > deadline {
        condition.unlock()
        throw stop.stopped ? CancellationError() : AudioPipelineFailure.stalled
      }
      readers += 1
      condition.wait(until: deadline)
      readers -= 1
    }
    condition.unlock()
    return try file.read(offset: offset, count: count, into: buffer, stop: stop)
  }
  func wake() { condition.withLock { condition.broadcast() } }
}

enum AudioFixtures {
  static let ffmpeg = [
    "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg",
  ]
  .first { FileManager.default.isExecutableFile(atPath: $0) }

  /// An MP3 with no Xing/Info/VBRI length header (as older rips have), made
  /// of pink-noise parts of `seconds` at `kbps` each, joined frame to frame.
  /// Core Audio estimates its length from the opening bitrate.
  static func headerlessMP3(at url: URL, parts: [(seconds: Int, kbps: Int)]) throws {
    var joined = Data()
    for (index, part) in parts.enumerated() {
      let piece = url.deletingLastPathComponent().appendingPathComponent(
        "part-\(index)-" + url.lastPathComponent)
      let encode = Process()
      encode.executableURL = URL(fileURLWithPath: ffmpeg!)
      encode.arguments = [
        "-v", "error", "-y", "-f", "lavfi", "-i", "anoisesrc=d=\(part.seconds):c=pink:a=0.3",
        "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "\(part.kbps)k",
        "-write_xing", "0", "-id3v2_version", "0", "-write_id3v1", "0", piece.path,
      ]
      try encode.run()
      encode.waitUntilExit()
      guard encode.terminationStatus == 0 else { throw AudioPipelineFailure.conversion }
      joined.append(try Data(contentsOf: piece))
      try FileManager.default.removeItem(at: piece)
    }
    guard joined.range(of: Data("Xing".utf8)) == nil, joined.range(of: Data("Info".utf8)) == nil
    else { throw AudioPipelineFailure.conversion }
    try joined.write(to: url)
  }

  /// Every remaining sample of one channel.
  static func drain(_ decoder: StreamingPCMDecoder, channel: Int = 1) async throws -> [Float] {
    var samples: [Float] = []
    while let block = try await decoder.read(maxFrames: 2048) {
      samples.append(
        contentsOf: UnsafeBufferPointer(
          start: block.floatChannelData![channel], count: Int(block.frameLength)))
    }
    return samples
  }
}
