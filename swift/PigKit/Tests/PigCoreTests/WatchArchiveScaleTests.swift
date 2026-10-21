import CryptoKit
import Foundation
import PigDomain
import PigDownloads
import PigStore
import Testing

private final class SmallCopy: URLProtocol, @unchecked Sendable {
  static let payload = Data(repeating: 7, count: 4096)
  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
  override func startLoading() {
    client?.urlProtocol(
      self,
      didReceive: HTTPURLResponse(
        url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
        headerFields: ["Content-Length": String(Self.payload.count)])!,
      cacheStoragePolicy: .notAllowed)
    client?.urlProtocol(self, didLoad: Self.payload)
    client?.urlProtocolDidFinishLoading(self)
  }
  override func stopLoading() {}
}

/// The Watch manifest asks the archive for every ready song every two
/// seconds while paired (two-week review, finding 6).
@Suite struct WatchArchiveScaleTests {
  static let count = 1000

  func archive(_ root: URL) throws -> DownloadArchive {
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [SmallCopy.self]
    return try DownloadArchive(directory: root, configuration: config)
  }

  func hex(_ data: Data) -> String { data.map { String(format: "%02x", $0) }.joined() }

  /// One verified transfer, cloned (hard-linked files) to `count` ready songs.
  func readyArchive(_ root: URL) async throws -> (DownloadArchive, [Track]) {
    let first = try archive(root)
    let song = try LibraryCodec.decoder().decode(
      Track.self, from: Data(#"{"id":"s0","title":"S","artist":"A","source_revision":"v1"}"#.utf8))
    try await first.enqueue([song], quality: "original")
    let hash = hex(Data(SHA256.hash(data: SmallCopy.payload)))
    let manifest = try LibraryCodec.decoder().decode(
      DeviceCopy.self,
      from: JSONSerialization.data(withJSONObject: [
        "state": "ready", "quality": "original", "sha256": hash, "source_sha256": hash,
        "bytes": SmallCopy.payload.count, "extension": "mp3", "key": "k",
      ]))
    let record = try #require(await first.snapshot().first)
    try await first.transfer(
      record, manifest: manifest, request: URLRequest(url: URL(string: "https://x.invalid/s")!),
      budget: 10_000_000)
    let index = root.appendingPathComponent("downloads.json")
    let template = try #require(
      try JSONSerialization.jsonObject(with: Data(contentsOf: index)) as? [[String: Any]]
    ).first!
    let original = try #require(template["file_name"] as? String)
    var rows: [[String: Any]] = []
    var tracks: [Track] = []
    for i in 0..<Self.count {
      let id = "s\(i)"
      let name = hex(Data(SHA256.hash(data: Data((id + "\noriginal").utf8)))) + ".mp3"
      if name != original {
        try FileManager.default.linkItem(
          at: root.appendingPathComponent(original), to: root.appendingPathComponent(name))
      }
      var row = template
      var track = try #require(row["track"] as? [String: Any])
      track["id"] = id
      row["id"] = id
      row["track"] = track
      row["file_name"] = name
      rows.append(row)
      let data = try JSONSerialization.data(withJSONObject: track)
      tracks.append(try LibraryCodec.decoder().decode(Track.self, from: data))
    }
    try JSONSerialization.data(withJSONObject: rows).write(to: index)
    return (try archive(root), tracks)
  }

  @Test func oneIndexedLookupFindsEveryReadySongLikeOneByOne() async throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    let (archive, tracks) = try await readyArchive(root)

    var clock = ContinuousClock.now
    var single: [String: URL] = [:]
    for track in tracks { single[track.id] = await archive.localFile(track) }
    let oneByOne = ContinuousClock.now - clock
    clock = ContinuousClock.now
    let batched = await archive.localFiles(tracks)
    let indexed = ContinuousClock.now - clock
    print("Watch archive, \(Self.count) ready songs: one by one \(oneByOne), indexed \(indexed)")

    #expect(single.count == Self.count)
    #expect(batched == single)
    // A stale source revision is still refused in the batch.
    var stale = tracks[0]
    stale.sourceRevision = "v2"
    #expect(await archive.localFiles([stale]).isEmpty)
  }

  @Test func theRevisionChangesWithEveryRecordChange() async throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    defer { try? FileManager.default.removeItem(at: root) }
    let (archive, tracks) = try await readyArchive(root)
    let start = await archive.revision
    #expect(await archive.revision == start)  // Reading changes nothing.
    _ = await archive.localFiles(tracks)
    #expect(await archive.revision == start)
    try await archive.remove(id: tracks[0].id)
    let removed = await archive.revision
    #expect(removed != start)
    #expect(await archive.localFiles([tracks[0]]).isEmpty)
    try await archive.clearFinished()
    #expect(await archive.revision != removed)
  }
}
