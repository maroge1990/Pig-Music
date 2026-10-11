import CoreGraphics
import Foundation
import ImageIO
import PigDomain
import PigStore
import Testing
import UniformTypeIdentifiers

private actor ArtworkFetch {
  private(set) var calls = 0
  let bytes: Data
  init(_ bytes: Data) { self.bytes = bytes }
  func read(_ request: ArtworkRequest) async throws -> Data {
    calls += 1
    try await Task.sleep(for: .milliseconds(30))
    return bytes
  }
}

private func artworkPNG(size: Int = 8) throws -> Data {
  let context = CGContext(
    data: nil, width: size, height: size, bitsPerComponent: 8,
    bytesPerRow: size * 4, space: CGColorSpaceCreateDeviceRGB(),
    bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
  context.setFillColor(CGColor(red: 0.9, green: 0.3, blue: 0.5, alpha: 1))
  context.fill(CGRect(x: 0, y: 0, width: size, height: size))
  let bytes = NSMutableData()
  let output = CGImageDestinationCreateWithData(bytes, UTType.png.identifier as CFString, 1, nil)!
  CGImageDestinationAddImage(output, context.makeImage()!, nil)
  #expect(CGImageDestinationFinalize(output))
  return bytes as Data
}

@Test func artworkCoalescesAndPersistsWithoutCrossAccountSharing() async throws {
  let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  defer { try? FileManager.default.removeItem(at: root) }
  let request = try ArtworkRequest(sha: String(repeating: "a", count: 64))
  let bytes = try artworkPNG()
  let source = ArtworkFetch(bytes)
  let directory = root.appendingPathComponent("person-one")
  let cache = try ArtworkCache(directory: directory)
  async let first = cache.data(for: request) { try await source.read($0) }
  async let second = cache.data(for: request) { try await source.read($0) }
  #expect(try await first == bytes)
  #expect(try await second == bytes)
  #expect(await source.calls == 1)
  let reopened = try ArtworkCache(directory: directory)
  #expect(try await reopened.data(for: request) { _ in throw ArtworkFailure.unavailable } == bytes)
  let other = try ArtworkCache(directory: root.appendingPathComponent("person-two"))
  await #expect(throws: ArtworkFailure.unavailable) {
    try await other.data(for: request) { _ in throw ArtworkFailure.unavailable }
  }
  let image = try ArtworkCache.thumbnail(bytes, width: 128)
  #expect(image.width == 8 && image.height == 8)
}

@Test func artworkRejectsUnsafeKeysMalformedImagesAndAllocationBounds() async throws {
  for sha in ["../secret", String(repeating: "A", count: 64), String(repeating: "a", count: 63)] {
    #expect(throws: ArtworkFailure.invalidRequest) { try ArtworkRequest(sha: sha) }
  }
  #expect(throws: ArtworkFailure.invalidRequest) {
    try ArtworkRequest(sha: String(repeating: "a", count: 64), width: 999)
  }
  let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  defer { try? FileManager.default.removeItem(at: root) }
  let cache = try ArtworkCache(directory: root)
  let request = try ArtworkRequest(sha: String(repeating: "b", count: 64), width: 128)
  await #expect(throws: ArtworkFailure.invalidImage) {
    try await cache.data(for: request) { _ in Data("<html>not artwork</html>".utf8) }
  }
  let largePixels = try artworkPNG(size: 129)
  await #expect(throws: ArtworkFailure.invalidImage) {
    try await cache.data(for: request) { _ in largePixels }
  }
  await #expect(throws: ArtworkFailure.tooLarge) {
    try await cache.data(for: request) { _ in
      Data(repeating: 0, count: ArtworkCache.maximumImageBytes + 1)
    }
  }
  #expect(try FileManager.default.contentsOfDirectory(atPath: root.path).isEmpty)
}

@Test func artworkBudgetEvictsAndCorruptionRefetches() async throws {
  let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  defer { try? FileManager.default.removeItem(at: root) }
  let bytes = try artworkPNG()
  let first = try ArtworkRequest(sha: String(repeating: "a", count: 64))
  let second = try ArtworkRequest(sha: String(repeating: "b", count: 64))
  let cache = try ArtworkCache(directory: root, budget: bytes.count)
  _ = try await cache.data(for: first) { _ in bytes }
  _ = try await cache.data(for: second) { _ in bytes }
  #expect(!FileManager.default.fileExists(atPath: root.appendingPathComponent(first.filename).path))
  #expect(FileManager.default.fileExists(atPath: root.appendingPathComponent(second.filename).path))
  try Data("broken".utf8).write(to: root.appendingPathComponent(second.filename))
  let source = ArtworkFetch(bytes)
  #expect(try await cache.data(for: second) { try await source.read($0) } == bytes)
  #expect(await source.calls == 1)
}

@Test func artworkCancelledWaiterDoesNotCancelAnotherView() async throws {
  let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  defer { try? FileManager.default.removeItem(at: root) }
  let bytes = try artworkPNG()
  let request = try ArtworkRequest(sha: String(repeating: "c", count: 64))
  let source = ArtworkFetch(bytes)
  let cache = try ArtworkCache(directory: root)
  let waiter = Task { try await cache.data(for: request) { try await source.read($0) } }
  while await source.calls == 0 { await Task.yield() }
  let other = Task { try await cache.data(for: request) { try await source.read($0) } }
  waiter.cancel()
  await #expect(throws: CancellationError.self) { try await waiter.value }
  #expect(try await other.value == bytes)
  #expect(await source.calls == 1)
}
