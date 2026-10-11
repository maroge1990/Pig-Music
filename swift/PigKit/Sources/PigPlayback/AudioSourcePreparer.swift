import Foundation

public enum AudioSourceFailure: Error, LocalizedError, Equatable {
  case invalidURL, busy, storageLimit, tooLarge, unavailable, invalidBody
  public var errorDescription: String? {
    switch self {
    case .invalidURL: "The audio source is not a secure media URL."
    case .busy: "Another audio source is being prepared."
    case .storageLimit: "Release an earlier playback source before preparing another song."
    case .tooLarge: "This song exceeds the temporary playback storage limit."
    case .unavailable: "The audio source is unavailable. Try again or play a saved song."
    case .invalidBody: "The source did not return an audio file."
    }
  }
}

/// An encoded file lease, not a durable offline download or a guarantee of codec support.
public struct PreparedAudioSource: Sendable {
  public let id: UUID
  public let file: URL
  public let byteCount: Int
  public init(id: UUID = UUID(), file: URL, byteCount: Int) {
    self.id = id
    self.file = file
    self.byteCount = byteCount
  }
}

private final class NoMediaRedirects: NSObject, URLSessionTaskDelegate, Sendable {
  func urlSession(
    _ session: URLSession, task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
    completionHandler: @escaping @Sendable (URLRequest?) -> Void
  ) { completionHandler(nil) }
}

/// One transfer at a time, with explicit leases for the current and upcoming songs.
/// The resolver owns authentication; media requests never receive a device bearer token.
public actor AudioSourcePreparer {
  private let directory: URL
  private let session: URLSession
  private let maximumFileBytes: Int
  private let maximumTotalBytes: Int
  private var leases: [UUID: PreparedAudioSource] = [:]
  private var transfer: Task<PreparedAudioSource, Error>?
  private var generation = 0

  public init(
    root: URL, maximumFileBytes: Int = 128 * 1024 * 1024,
    maximumTotalBytes: Int = 256 * 1024 * 1024,
    configuration: URLSessionConfiguration = .ephemeral
  ) throws {
    guard root.isFileURL, maximumFileBytes > 0, maximumTotalBytes >= maximumFileBytes else {
      throw AudioSourceFailure.storageLimit
    }
    self.maximumFileBytes = maximumFileBytes
    self.maximumTotalBytes = maximumTotalBytes
    directory = root.appendingPathComponent("playback-" + UUID().uuidString, isDirectory: true)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    configuration.urlCache = nil
    configuration.urlCredentialStorage = nil
    configuration.httpAdditionalHeaders = nil
    configuration.httpCookieStorage = nil
    configuration.httpShouldSetCookies = false
    configuration.timeoutIntervalForRequest = 20
    configuration.timeoutIntervalForResource = 120
    session = URLSession(
      configuration: configuration, delegate: NoMediaRedirects(), delegateQueue: nil)
  }

  deinit {
    transfer?.cancel()
    session.invalidateAndCancel()
    try? FileManager.default.removeItem(at: directory)
  }

  public func prepare(
    resolve: @escaping @Sendable () async throws -> URL
  ) async throws -> PreparedAudioSource {
    try Task.checkCancellation()
    guard transfer == nil else { throw AudioSourceFailure.busy }
    let retained = leases.values.reduce(0) { $0 + $1.byteCount }
    guard retained <= maximumTotalBytes - maximumFileBytes else {
      throw AudioSourceFailure.storageLimit
    }
    let stamp = generation
    let directory = directory
    let session = session
    let limit = maximumFileBytes
    let task = Task {
      // A signed link can expire between resolution and its first request. Refresh once only.
      for attempt in 0..<2 {
        try Task.checkCancellation()
        let url = try await resolve()
        guard url.scheme?.lowercased() == "https", url.host != nil,
          url.user == nil, url.password == nil, url.fragment == nil
        else {
          throw AudioSourceFailure.invalidURL
        }
        try Task.checkCancellation()
        var request = URLRequest(url: url)
        request.setValue("audio/*,application/octet-stream", forHTTPHeaderField: "Accept")
        let (bytes, rawResponse) = try await session.bytes(for: request)
        defer { bytes.task.cancel() }
        guard let response = rawResponse as? HTTPURLResponse else {
          throw AudioSourceFailure.unavailable
        }
        if [401, 403].contains(response.statusCode), attempt == 0 { continue }
        guard response.statusCode == 200 else { throw AudioSourceFailure.unavailable }
        let mime = response.mimeType?.lowercased() ?? ""
        guard mime.hasPrefix("audio/") || mime == "application/octet-stream" else {
          throw AudioSourceFailure.invalidBody
        }
        guard response.expectedContentLength <= limit else { throw AudioSourceFailure.tooLarge }
        let id = UUID()
        let allowedExtensions = ["wav", "aiff", "aif", "m4a", "mp3", "flac", "ogg", "opus", "aac"]
        let mimeExtensions = [
          "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
          "audio/aiff": "aiff", "audio/x-aiff": "aiff", "audio/mpeg": "mp3",
          "audio/mp4": "m4a", "audio/x-m4a": "m4a", "audio/aac": "aac",
          "audio/flac": "flac", "audio/x-flac": "flac", "audio/ogg": "ogg",
          "audio/opus": "opus",
        ]
        let suffix = mimeExtensions[mime] ?? url.pathExtension.lowercased()
        let file = directory.appendingPathComponent(id.uuidString)
          .appendingPathExtension(allowedExtensions.contains(suffix) ? suffix : "media")
        let partial = file.appendingPathExtension("partial")
        guard FileManager.default.createFile(atPath: partial.path, contents: nil) else {
          throw AudioSourceFailure.storageLimit
        }
        defer { try? FileManager.default.removeItem(at: partial) }
        let handle = try FileHandle(forWritingTo: partial)
        defer { try? handle.close() }
        var chunk = Data()
        var count = 0
        chunk.reserveCapacity(65536)
        for try await byte in bytes {
          if count % 4096 == 0 { try Task.checkCancellation() }
          guard count < limit else { throw AudioSourceFailure.tooLarge }
          count += 1
          chunk.append(byte)
          if chunk.count == 65536 {
            try handle.write(contentsOf: chunk)
            chunk.removeAll(keepingCapacity: true)
          }
        }
        try Task.checkCancellation()
        guard count > 0,
          response.expectedContentLength < 0 || response.expectedContentLength == count
        else {
          throw AudioSourceFailure.invalidBody
        }
        try handle.write(contentsOf: chunk)
        try handle.close()
        try FileManager.default.moveItem(at: partial, to: file)
        return PreparedAudioSource(id: id, file: file, byteCount: count)
      }
      throw AudioSourceFailure.unavailable
    }
    transfer = task
    defer { transfer = nil }
    let result = try await withTaskCancellationHandler {
      try await task.value
    } onCancel: {
      task.cancel()
    }
    guard !Task.isCancelled, generation == stamp else {
      try? FileManager.default.removeItem(at: result.file)
      throw CancellationError()
    }
    leases[result.id] = result
    return result
  }

  /// Stage a trusted local file (for the synthetic demo or a future offline repository).
  /// Remote source resolution still goes through the HTTPS-only prepare operation.
  public func stageLocalFile(_ source: URL) throws -> PreparedAudioSource {
    try Task.checkCancellation()
    guard source.isFileURL else { throw AudioSourceFailure.invalidURL }
    guard transfer == nil else { throw AudioSourceFailure.busy }
    let retained = leases.values.reduce(0) { $0 + $1.byteCount }
    guard retained <= maximumTotalBytes - maximumFileBytes else {
      throw AudioSourceFailure.storageLimit
    }
    let input = try FileHandle(forReadingFrom: source)
    defer { try? input.close() }
    let id = UUID()
    let extensions = ["wav", "aiff", "aif", "m4a", "mp3", "flac", "ogg", "opus", "aac"]
    let suffix = source.pathExtension.lowercased()
    let destination = directory.appendingPathComponent(id.uuidString)
      .appendingPathExtension(extensions.contains(suffix) ? suffix : "media")
    let partial = destination.appendingPathExtension("partial")
    guard FileManager.default.createFile(atPath: partial.path, contents: nil) else {
      throw AudioSourceFailure.storageLimit
    }
    defer { try? FileManager.default.removeItem(at: partial) }
    let handle = try FileHandle(forWritingTo: partial)
    defer { try? handle.close() }
    var count = 0
    while let chunk = try input.read(upToCount: 65536), !chunk.isEmpty {
      try Task.checkCancellation()
      guard chunk.count <= maximumFileBytes - count else { throw AudioSourceFailure.tooLarge }
      count += chunk.count
      try handle.write(contentsOf: chunk)
    }
    guard count > 0 else { throw AudioSourceFailure.invalidBody }
    try Task.checkCancellation()
    try handle.close()
    try FileManager.default.moveItem(at: partial, to: destination)
    let result = PreparedAudioSource(id: id, file: destination, byteCount: count)
    leases[id] = result
    return result
  }

  public func release(_ source: PreparedAudioSource) {
    guard let owned = leases.removeValue(forKey: source.id) else { return }
    try? FileManager.default.removeItem(at: owned.file)
  }

  /// Call after stopping the decoder on account/queue replacement. Pending work cannot publish.
  public func reset() {
    generation += 1
    transfer?.cancel()
    for source in leases.values { try? FileManager.default.removeItem(at: source.file) }
    leases.removeAll()
  }
}
