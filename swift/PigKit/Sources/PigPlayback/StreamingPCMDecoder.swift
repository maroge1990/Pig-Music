import AVFoundation
import Foundation

#if !os(watchOS)

  /// Decodes one song from `AudioBytes`, local or still arriving. It parses the
  /// file with the same Core Audio reader AVAudioFile uses (so gapless lengths
  /// and encoder padding are handled the same), through callbacks that wait for
  /// missing bytes. Every call runs on the decoder's own queue, where waiting
  /// blocks only that queue; a cancelled caller stops the wait.
  final class StreamingPCMDecoder: @unchecked Sendable {
    /// The callbacks' view of the bytes.
    private final class Reader: @unchecked Sendable {
      let bytes: any AudioBytes
      let stop = ReadStop()
      var failure: Error?
      init(_ bytes: any AudioBytes) { self.bytes = bytes }
    }
    private struct Decoded: @unchecked Sendable { let buffer: AVAudioPCMBuffer? }

    let expectedFrames: Int64
    /// False when `expectedFrames` is an estimate: decoding then runs to the
    /// file's end instead of stopping at the expected length.
    private let exactLength: Bool
    /// The song's length as known so far, in output frames. An estimate (see
    /// `lengthIsExact`) is measured once every byte has arrived, never falls
    /// behind the audio decoded, and is the decoded length at the end. Read
    /// it after `open` or `read` returns.
    private(set) var lengthFrames: Int64
    private(set) var lengthIsExact: Bool
    private let sourceRate: Double
    private let queue = DispatchQueue(label: "pig.playback.decoder", qos: .userInitiated)
    private let reader: Reader
    private let context: Unmanaged<Reader>
    private let audioFile: AudioFileID
    private let file: ExtAudioFileRef
    private let converter: AVAudioConverter
    private let input: AVAudioPCMBuffer
    private let format: AVAudioFormat
    private var delivered: Int64 = 0
    private var ended = false

    private init(
      reader: Reader, context: Unmanaged<Reader>, audioFile: AudioFileID, file: ExtAudioFileRef,
      converter: AVAudioConverter, input: AVAudioPCMBuffer, format: AVAudioFormat,
      expectedFrames: Int64, exactLength: Bool, delivered: Int64, sourceRate: Double
    ) {
      self.reader = reader
      self.context = context
      self.audioFile = audioFile
      self.file = file
      self.converter = converter
      self.input = input
      self.format = format
      self.expectedFrames = expectedFrames
      self.exactLength = exactLength
      self.delivered = delivered
      self.sourceRate = sourceRate
      lengthFrames = exactLength ? expectedFrames : max(expectedFrames, delivered)
      lengthIsExact = exactLength
    }
    deinit {
      ExtAudioFileDispose(file)
      AudioFileClose(audioFile)
      context.release()
    }

    /// Opens a prepared song for decoding into `format`, from `startSeconds` in.
    static func open(
      _ source: PreparedAudioSource, format: AVAudioFormat, startSeconds: Double = 0
    ) async throws -> StreamingPCMDecoder {
      try await open(
        source.audioBytes(), typeHint: typeHint(for: source.file), format: format,
        startSeconds: startSeconds)
    }

    /// Opens a song for decoding into `format`, from `startSeconds` in.
    static func open(
      _ bytes: any AudioBytes, typeHint: AudioFileTypeID = 0, format: AVAudioFormat,
      startSeconds: Double = 0
    ) async throws -> StreamingPCMDecoder {
      guard startSeconds.isFinite, startSeconds >= 0 else {
        throw AudioPipelineFailure.invalidConfiguration
      }
      let reader = Reader(bytes)
      let queue = DispatchQueue(label: "pig.playback.decoder-open", qos: .userInitiated)
      let opened = try await withTaskCancellationHandler {
        try await withCheckedThrowingContinuation {
          (continuation: CheckedContinuation<StreamingPCMDecoder, Error>) in
          queue.async {
            continuation.resume(
              with: Result {
                try make(reader, typeHint: typeHint, format: format, startSeconds: startSeconds)
              })
          }
        }
      } onCancel: {
        reader.stop.stop()
        bytes.wake()
      }
      return opened
    }

    private static func make(
      _ reader: Reader, typeHint: AudioFileTypeID, format: AVAudioFormat, startSeconds: Double
    ) throws -> StreamingPCMDecoder {
      let context = Unmanaged.passRetained(reader)
      var audioFile: AudioFileID?
      var status = AudioFileOpenWithCallbacks(
        context.toOpaque(), readBytes, nil, byteCount, nil, typeHint, &audioFile)
      guard status == noErr, let audioFile else {
        context.release()
        throw reader.failure ?? AudioPipelineFailure.conversion
      }
      var wrapped: ExtAudioFileRef?
      status = ExtAudioFileWrapAudioFileID(audioFile, false, &wrapped)
      guard status == noErr, let file = wrapped else {
        AudioFileClose(audioFile)
        context.release()
        throw reader.failure ?? AudioPipelineFailure.conversion
      }
      func dispose() {
        ExtAudioFileDispose(file)
        AudioFileClose(audioFile)
        context.release()
      }
      do {
        var description = AudioStreamBasicDescription()
        var size = UInt32(MemoryLayout<AudioStreamBasicDescription>.size)
        try check(
          ExtAudioFileGetProperty(file, kExtAudioFileProperty_FileDataFormat, &size, &description),
          reader)
        var length: Int64 = 0
        // An MP3 without a Xing/Info/VBRI header states no length: Core Audio
        // counts it by reading every frame, which waits for the whole file.
        // Such a song starts from an estimate and plays to its real end;
        // once all of it is here, counting no longer waits.
        let exact =
          reader.bytes.complete || !isMP3(audioFile) || hasMP3LengthHeader(reader)
        if exact {
          size = UInt32(MemoryLayout<Int64>.size)
          try check(
            ExtAudioFileGetProperty(file, kExtAudioFileProperty_FileLengthFrames, &size, &length),
            reader)
        } else {
          var seconds: Float64 = 0
          size = UInt32(MemoryLayout<Float64>.size)
          try check(
            AudioFileGetProperty(audioFile, kAudioFilePropertyEstimatedDuration, &size, &seconds),
            reader)
          guard seconds.isFinite, seconds > 0 else { throw AudioPipelineFailure.emptyAudio }
          length = Int64((seconds * description.mSampleRate).rounded())
        }
        let channels = description.mChannelsPerFrame
        let rate = description.mSampleRate
        guard length > 0 else { throw AudioPipelineFailure.emptyAudio }
        guard (1...2).contains(channels) else { throw AudioPipelineFailure.unsupportedChannels }
        guard rate.isFinite, rate > 0,
          let client = AVAudioFormat(
            commonFormat: .pcmFormatFloat32, sampleRate: rate, channels: channels,
            interleaved: false)
        else { throw AudioPipelineFailure.invalidConfiguration }
        var clientDescription = client.streamDescription.pointee
        try check(
          ExtAudioFileSetProperty(
            file, kExtAudioFileProperty_ClientDataFormat,
            UInt32(MemoryLayout<AudioStreamBasicDescription>.size), &clientDescription),
          reader)
        guard let converter = AVAudioConverter(from: client, to: format),
          let input = AVAudioPCMBuffer(pcmFormat: client, frameCapacity: 8192)
        else { throw AudioPipelineFailure.conversion }
        // No leading/trailing resampler prime frames are added to the song's output timeline.
        converter.primeMethod = .none
        let frames = (Double(length) * format.sampleRate / rate).rounded()
        guard frames.isFinite, frames >= 1, frames < Double(Int64.max) else {
          throw AudioPipelineFailure.invalidConfiguration
        }
        // An estimate may be short: a later position can still be in the song.
        let position = (startSeconds * rate).rounded()
        let start = exact ? min(Double(length), position) : position
        if start > 0 { try check(ExtAudioFileSeek(file, Int64(start)), reader) }
        let expected = Int64(frames)
        let skipped = Int64((start * format.sampleRate / rate).rounded())
        return StreamingPCMDecoder(
          reader: reader, context: context, audioFile: audioFile, file: file,
          converter: converter, input: input, format: format, expectedFrames: expected,
          exactLength: exact, delivered: exact ? min(expected, skipped) : skipped,
          sourceRate: rate)
      } catch {
        dispose()
        throw error
      }
    }

    /// The next decoded block, or nil at the end of the song.
    func read(maxFrames: Int) async throws -> AVAudioPCMBuffer? {
      let decoded = try await withTaskCancellationHandler {
        try await withCheckedThrowingContinuation {
          (continuation: CheckedContinuation<Decoded, Error>) in
          queue.async { [self] in
            continuation.resume(with: Result { Decoded(buffer: try decode(maxFrames: maxFrames)) })
          }
        }
      } onCancel: { [reader] in
        reader.stop.stop()
        reader.bytes.wake()
      }
      return decoded.buffer
    }

    private func decode(maxFrames: Int) throws -> AVAudioPCMBuffer? {
      guard !ended, !exactLength || delivered < expectedFrames else { return nil }
      let capacity = exactLength ? min(maxFrames, Int(expectedFrames - delivered)) : maxFrames
      guard capacity > 0,
        let output = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: AVAudioFrameCount(capacity))
      else { throw AudioPipelineFailure.invalidConfiguration }
      for _ in 0..<16 {
        var failure: Error?
        var error: NSError?
        let status = converter.convert(to: output, error: &error) { [self] packets, status in
          input.frameLength = min(packets, input.frameCapacity)
          var frames = input.frameLength
          let result = ExtAudioFileRead(file, &frames, input.mutableAudioBufferList)
          guard result == noErr else {
            failure = reader.failure ?? AudioPipelineFailure.conversion
            status.pointee = .endOfStream
            return nil
          }
          input.frameLength = frames
          if frames == 0 {
            status.pointee = .endOfStream
            return nil
          }
          status.pointee = .haveData
          return input
        }
        if let failure { throw failure }
        if let error { throw error }
        if status == .error { throw AudioPipelineFailure.conversion }
        if status == .endOfStream { ended = true }
        if output.frameLength > 0 {
          delivered += Int64(output.frameLength)
          if !exactLength { measureLength() }
          return output
        }
        if ended {
          if !exactLength { measureLength() }
          return nil
        }
      }
      throw AudioPipelineFailure.stalled
    }

    /// Brings an estimated length up to date: the decoded length at the end,
    /// Core Audio's count once every byte is here, else at least what has
    /// been decoded.
    private func measureLength() {
      if ended {
        lengthFrames = delivered
        lengthIsExact = true
        return
      }
      if !lengthIsExact, reader.bytes.complete {
        var length: Int64 = 0
        var size = UInt32(MemoryLayout<Int64>.size)
        if ExtAudioFileGetProperty(file, kExtAudioFileProperty_FileLengthFrames, &size, &length)
          == noErr, length > 0
        {
          lengthFrames = Int64((Double(length) * format.sampleRate / sourceRate).rounded())
          lengthIsExact = true
        }
      }
      lengthFrames = max(lengthFrames, delivered)
    }

    private static func check(_ status: OSStatus, _ reader: Reader) throws {
      guard status == noErr else { throw reader.failure ?? AudioPipelineFailure.conversion }
    }

    private static func isMP3(_ audioFile: AudioFileID) -> Bool {
      var type: AudioFileTypeID = 0
      var size = UInt32(MemoryLayout<AudioFileTypeID>.size)
      return AudioFileGetProperty(audioFile, kAudioFilePropertyFileFormat, &size, &type) == noErr
        && type == kAudioFileMP3Type
    }

    /// Whether the first MP3 frame (after any ID3v2 tag) is a Xing, Info or
    /// VBRI header that states the song's length. Unreadable: assume it does,
    /// so Core Audio measures the length as before.
    private static func hasMP3LengthHeader(_ reader: Reader) -> Bool {
      func bytes(_ offset: Int, _ count: Int) -> [UInt8]? {
        var data = [UInt8](repeating: 0, count: count)
        guard
          let read = try? data.withUnsafeMutableBytes({
            try reader.bytes.read(
              offset: offset, count: count, into: $0.baseAddress!, stop: reader.stop)
          })
        else { return nil }
        return Array(data.prefix(read))
      }
      guard let tag = bytes(0, 10) else { return true }
      var start = 0
      if tag.count == 10, tag[0] == 0x49, tag[1] == 0x44, tag[2] == 0x33 {
        // Syncsafe size, plus the footer when its flag is set.
        start = 10 + tag[6...9].reduce(0) { $0 << 7 | Int($1 & 0x7F) }
        if tag[5] & 0x10 != 0 { start += 10 }
      }
      guard let window = bytes(start, 4096) else { return true }
      guard
        let sync = window.indices.dropLast(1).first(where: {
          window[$0] == 0xFF && window[$0 + 1] & 0xE0 == 0xE0
        })
      else { return true }
      let frame = Array(window[sync...].prefix(200))
      return ["Xing", "Info", "VBRI"].contains { marker in
        let pattern = Array(marker.utf8)
        return frame.count >= pattern.count
          && (0...(frame.count - pattern.count)).contains {
            Array(frame[$0..<$0 + pattern.count]) == pattern
          }
      }
    }

    /// The Core Audio file type for a file name, or 0 to let it look.
    static func typeHint(for file: URL) -> AudioFileTypeID {
      switch file.pathExtension.lowercased() {
      case "mp3": kAudioFileMP3Type
      case "m4a", "mp4": kAudioFileM4AType
      case "aac": kAudioFileAAC_ADTSType
      case "flac": kAudioFileFLACType
      case "wav": kAudioFileWAVEType
      case "aif", "aiff": kAudioFileAIFFType
      case "caf": kAudioFileCAFType
      default: 0
      }
    }
  }

  private func readBytes(
    _ client: UnsafeMutableRawPointer, _ position: Int64, _ requestCount: UInt32,
    _ buffer: UnsafeMutableRawPointer, _ actualCount: UnsafeMutablePointer<UInt32>
  ) -> OSStatus {
    let reader = Unmanaged<AnyObject>.fromOpaque(client).takeUnretainedValue()
    return StreamingPCMDecoder.callbackRead(
      reader, position: position, count: requestCount, buffer: buffer, actual: actualCount)
  }

  private func byteCount(_ client: UnsafeMutableRawPointer) -> Int64 {
    let reader = Unmanaged<AnyObject>.fromOpaque(client).takeUnretainedValue()
    return StreamingPCMDecoder.callbackLength(reader)
  }

  extension StreamingPCMDecoder {
    fileprivate static func callbackRead(
      _ object: AnyObject, position: Int64, count: UInt32, buffer: UnsafeMutableRawPointer,
      actual: UnsafeMutablePointer<UInt32>
    ) -> OSStatus {
      guard let reader = object as? Reader else { return kAudioFileUnspecifiedError }
      do {
        let read = try reader.bytes.read(
          offset: Int(position), count: Int(count), into: buffer, stop: reader.stop)
        actual.pointee = UInt32(read)
        return read == 0 && count > 0 ? kAudioFileEndOfFileError : noErr
      } catch {
        reader.failure = error
        actual.pointee = 0
        return kAudioFileUnspecifiedError
      }
    }
    fileprivate static func callbackLength(_ object: AnyObject) -> Int64 {
      guard let reader = object as? Reader else { return 0 }
      return Int64(reader.bytes.length)
    }
  }

#else

  /// watchOS has no Core Audio file callbacks: songs decode from complete files
  /// (the Watch plays its own downloads, never this engine's remote sources).
  final class StreamingPCMDecoder: @unchecked Sendable {
    private let decoder: PCMFileDecoder
    var expectedFrames: Int64 { decoder.expectedFrames }
    var lengthFrames: Int64 { decoder.expectedFrames }
    var lengthIsExact: Bool { true }
    private init(_ decoder: PCMFileDecoder) { self.decoder = decoder }
    static func open(
      _ source: PreparedAudioSource, format: AVAudioFormat, startSeconds: Double = 0
    ) async throws -> StreamingPCMDecoder {
      StreamingPCMDecoder(
        try PCMFileDecoder(url: source.file, format: format, startSeconds: startSeconds))
    }
    func read(maxFrames: Int) async throws -> AVAudioPCMBuffer? {
      try decoder.read(maxFrames: maxFrames)
    }
  }

#endif
