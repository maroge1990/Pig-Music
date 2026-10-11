import CryptoKit
import Foundation
import PigDomain

private final class NoDownloadRedirect: NSObject, URLSessionTaskDelegate, Sendable {
  func urlSession(
    _ session: URLSession, task: URLSessionTask,
    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
    completionHandler: @escaping @Sendable (URLRequest?) -> Void
  ) { completionHandler(nil) }
}

/// Durable, account-bound foreground downloads. Incomplete transfers restart safely.
public actor DownloadArchive {
  private let directory: URL
  private let session: URLSession
  private var records: [DownloadRecord]
  private var invalidated: Set<String> = []
  public init(directory: URL, configuration: URLSessionConfiguration = .ephemeral) throws {
    self.directory = directory
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    configuration.allowsCellularAccess = false
    configuration.httpShouldSetCookies = false
    configuration.urlCache = nil
    configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
    session = URLSession(
      configuration: configuration, delegate: NoDownloadRedirect(), delegateQueue: nil)
    let manifest = directory.appendingPathComponent("downloads.json")
    if FileManager.default.fileExists(atPath: manifest.path) {
      records =
        (try? LibraryCodec.decoder().decode(
          [DownloadRecord].self, from: Data(contentsOf: manifest))) ?? []
      for index in records.indices where records[index].state == "downloading" {
        records[index].state = "queued"
        records[index].bytes = 0
      }
    } else {
      records = []
    }
    let retainedNames = Set(records.filter { $0.state == "ready" }.compactMap(\.fileName))
    for file in try FileManager.default.contentsOfDirectory(
      at: directory, includingPropertiesForKeys: nil)
    where file.pathExtension == "partial"
      || (file.lastPathComponent != "downloads.json"
        && !retainedNames.contains(file.lastPathComponent))
    { try? FileManager.default.removeItem(at: file) }
  }
  public func snapshot() -> [DownloadRecord] { records }
  public func usedBytes() -> Int64 {
    records.filter { $0.state == "ready" }.reduce(0) { $0 + $1.total }
  }
  private func persist() throws {
    try LibraryCodec.encoder().encode(records).write(
      to: directory.appendingPathComponent("downloads.json"), options: .atomic)
  }
  public func enqueue(_ tracks: [Track], quality: String) throws {
    guard ["original", "aac"].contains(quality), tracks.count <= 10000 else {
      throw OfflineFailure.unsafeResponse
    }
    for track in tracks where track.serverState == nil || track.serverState == "in_library" {
      if let index = records.firstIndex(where: { $0.id == track.id }) {
        if records[index].state == "ready" && records[index].quality == quality
          && records[index].track.sourceRevision == track.sourceRevision
        {
          continue
        }
        if records[index].state == "downloading" { continue }
        if let name = records[index].fileName {
          try? FileManager.default.removeItem(at: directory.appendingPathComponent(name))
        }
        records[index] = DownloadRecord(track: track, quality: quality)
      } else {
        records.append(DownloadRecord(track: track, quality: quality))
      }
      invalidated.remove(track.id)
    }
    try persist()
  }
  public func localFile(_ track: Track) -> URL? {
    guard !invalidated.contains(track.id),
      let record = records.first(where: { $0.id == track.id && $0.state == "ready" }),
      record.track.sourceRevision == track.sourceRevision, let name = record.fileName,
      name
        == safeName(
          track.id, quality: record.quality,
          extension: name.split(separator: ".").last.map(String.init) ?? ""),
      let size = try? directory.appendingPathComponent(name).resourceValues(forKeys: [.fileSizeKey])
        .fileSize, Int64(size) == record.total
    else { return nil }
    return directory.appendingPathComponent(name)
  }
  private func safeName(_ id: String, quality: String, extension ext: String) -> String {
    SHA256.hash(data: Data((id + "\n" + quality).utf8)).map { String(format: "%02x", $0) }.joined()
      + "." + ext
  }
  public func remove(id: String) throws {
    invalidated.insert(id)
    if let record = records.first(where: { $0.id == id }), let name = record.fileName {
      let ext = name.split(separator: ".").last.map(String.init) ?? ""
      if name == safeName(id, quality: record.quality, extension: ext) {
        try? FileManager.default.removeItem(at: directory.appendingPathComponent(name))
      }
    }
    records.removeAll { $0.id == id }
    try persist()
  }
  public func reconcile(_ allowed: [String: String?]) throws {
    for record in records {
      guard let revision = allowed[record.id], revision == record.track.sourceRevision else {
        try remove(id: record.id)
        continue
      }
    }
  }
  public func clear() throws {
    invalidated.formUnion(records.map(\.id))
    records = []
    for file in try FileManager.default.contentsOfDirectory(
      at: directory, includingPropertiesForKeys: nil)
    { try? FileManager.default.removeItem(at: file) }
    try persist()
  }
  public func interruptRunning() throws {
    for index in records.indices where records[index].state == "downloading" {
      records[index].state = "queued"
      records[index].bytes = 0
    }
    try persist()
  }
  public func fail(id: String, message: String) throws {
    guard let index = records.firstIndex(where: { $0.id == id }) else { return }
    records[index].state = "failed"
    records[index].error = message
    try persist()
  }
  public func transfer(
    _ record: DownloadRecord, manifest: DeviceCopy, request: URLRequest, budget: Int64,
    onProgress: @Sendable (Int64, Int64) async -> Void = { _, _ in }
  ) async throws {
    let extensions = [
      "mp3", "m4a", "aac", "flac", "ogg", "opus", "wav", "aiff", "aif", "wma", "ape", "wv",
    ]
    guard request.url?.scheme == "https", manifest.state == "ready", let expected = manifest.sha256,
      expected.count == 64, expected.allSatisfy({ "0123456789abcdef".contains($0) }),
      manifest.quality == record.quality, extensions.contains(manifest.fileExtension),
      manifest.bytes > 0
    else { throw OfflineFailure.unsafeResponse }
    guard usedBytes() + manifest.bytes <= budget else { throw OfflineFailure.quota }
    guard let index = records.firstIndex(where: { $0.id == record.id }),
      !invalidated.contains(record.id)
    else { throw OfflineFailure.cancelled }
    records[index].state = "downloading"
    records[index].total = manifest.bytes
    records[index].error = nil
    try persist()
    await onProgress(0, manifest.bytes)
    let name = safeName(record.id, quality: record.quality, extension: manifest.fileExtension)
    let temporary = directory.appendingPathComponent(name + ".partial")
    let output = directory.appendingPathComponent(name)
    FileManager.default.createFile(atPath: temporary.path, contents: nil)
    let file = try FileHandle(forWritingTo: temporary)
    defer {
      try? file.close()
      try? FileManager.default.removeItem(at: temporary)
    }
    let (stream, response) = try await session.bytes(for: request)
    guard let http = response as? HTTPURLResponse else { throw OfflineFailure.unsafeResponse }
    if http.statusCode == 401 { throw OfflineFailure.authentication }
    guard http.statusCode == 200, response.url == request.url,
      response.mimeType != "application/json", response.mimeType != "text/html",
      response.expectedContentLength < 0 || response.expectedContentLength == manifest.bytes
    else { throw OfflineFailure.unsafeResponse }
    var digest = SHA256()
    var block = Data()
    var bytes: Int64 = 0
    var lastReport: Int64 = 0
    for try await byte in stream {
      block.append(byte)
      bytes += 1
      guard bytes <= manifest.bytes else { throw OfflineFailure.integrity }
      if block.count == 65536 {
        try Task.checkCancellation()
        guard !invalidated.contains(record.id), records.contains(where: { $0.id == record.id })
        else { throw OfflineFailure.cancelled }
        try file.write(contentsOf: block)
        digest.update(data: block)
        block.removeAll(keepingCapacity: true)
      }
      if bytes - lastReport >= 512 * 1024 {
        lastReport = bytes
        await onProgress(bytes, manifest.bytes)
      }
    }
    try Task.checkCancellation()
    guard !invalidated.contains(record.id),
      let index = records.firstIndex(where: { $0.id == record.id })
    else { throw OfflineFailure.cancelled }
    if !block.isEmpty {
      try file.write(contentsOf: block)
      digest.update(data: block)
    }
    guard bytes == manifest.bytes,
      digest.finalize().map({ String(format: "%02x", $0) }).joined() == expected
    else { throw OfflineFailure.integrity }
    try file.synchronize()
    try file.close()
    if FileManager.default.fileExists(atPath: output.path) {
      try FileManager.default.removeItem(at: output)
    }
    try FileManager.default.moveItem(at: temporary, to: output)
    records[index].state = "ready"
    records[index].bytes = bytes
    records[index].total = bytes
    records[index].fileName = name
    records[index].checksum = expected
    do { try persist() } catch {
      records[index].state = "failed"
      try? FileManager.default.removeItem(at: output)
      throw error
    }
    await onProgress(bytes, manifest.bytes)
  }
}
