import Foundation
import ImageIO
import PigDomain

/// One cache per server/person namespace. Encoded bytes are bounded independently of image pixels.
public actor ArtworkCache {
  public static let maximumImageBytes = 2 * 1024 * 1024
  private struct Entry {
    var size: Int
    var used: Date
  }
  private struct Flight {
    let id: UUID
    let task: Task<Data, Error>
  }
  private let directory: URL
  private let budget: Int
  private var entries: [String: Entry] = [:]
  private var flights: [ArtworkRequest: Flight] = [:]
  private var storedBytes = 0

  public init(directory: URL, budget: Int = 64 * 1024 * 1024) throws {
    self.directory = directory
    self.budget = max(0, budget)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    for file in try FileManager.default.contentsOfDirectory(
      at: directory, includingPropertiesForKeys: [.fileSizeKey, .contentModificationDateKey])
    {
      guard file.pathExtension == "image" else { continue }
      let values = try file.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey])
      let size = values.fileSize ?? 0
      if size > 0 && size <= Self.maximumImageBytes {
        entries[file.lastPathComponent] = Entry(
          size: size, used: values.contentModificationDate ?? .distantPast)
        storedBytes += size
      } else {
        try? FileManager.default.removeItem(at: file)
      }
    }
  }

  public func data(
    for request: ArtworkRequest,
    fetch: @escaping @Sendable (ArtworkRequest) async throws -> Data
  ) async throws -> Data {
    try Task.checkCancellation()
    trim()
    let file = directory.appendingPathComponent(request.filename)
    if entries[request.filename] != nil {
      let size = (try? file.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0
      if size > 0, size <= Self.maximumImageBytes, let data = try? Data(contentsOf: file),
        (try? Self.validate(data, width: request.width)) != nil
      {
        let used = Date()
        entries[request.filename]?.used = used
        try? FileManager.default.setAttributes([.modificationDate: used], ofItemAtPath: file.path)
        return data
      }
      storedBytes -= entries.removeValue(forKey: request.filename)?.size ?? 0
      try? FileManager.default.removeItem(at: file)
    }
    let flight: Flight
    if let pending = flights[request] {
      flight = pending
    } else {
      flight = Flight(
        id: UUID(),
        task: Task {
          let data = try await fetch(request)
          try Self.validate(data, width: request.width)
          return data
        })
      flights[request] = flight
    }
    do {
      let data = try await flight.task.value
      if flights[request]?.id == flight.id {
        flights.removeValue(forKey: request)
        // Disk cache failure never prevents otherwise valid artwork from displaying.
        if data.count <= budget, (try? data.write(to: file, options: .atomic)) != nil {
          entries[request.filename] = Entry(size: data.count, used: Date())
          storedBytes += data.count
          trim()
        }
      }
      try Task.checkCancellation()
      return data
    } catch {
      if flights[request]?.id == flight.id { flights.removeValue(forKey: request) }
      throw error
    }
  }

  public func cancelPending() {
    for flight in flights.values { flight.task.cancel() }
    flights.removeAll()
  }

  public static func thumbnail(_ data: Data, width: Int) throws -> CGImage {
    try validate(data, width: width)
    guard
      let source = CGImageSourceCreateWithData(
        data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
      let image = CGImageSourceCreateThumbnailAtIndex(
        source, 0,
        [
          kCGImageSourceCreateThumbnailFromImageAlways: true,
          kCGImageSourceCreateThumbnailWithTransform: true,
          kCGImageSourceShouldCacheImmediately: true,
          kCGImageSourceThumbnailMaxPixelSize: width,
        ] as CFDictionary)
    else { throw ArtworkFailure.invalidImage }
    return image
  }

  private static func validate(_ data: Data, width: Int) throws {
    guard !data.isEmpty, data.count <= maximumImageBytes else { throw ArtworkFailure.tooLarge }
    guard
      let source = CGImageSourceCreateWithData(
        data as CFData, [kCGImageSourceShouldCache: false] as CFDictionary),
      CGImageSourceGetCount(source) == 1,
      let properties = CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any],
      let w = properties[kCGImagePropertyPixelWidth] as? Int,
      let h = properties[kCGImagePropertyPixelHeight] as? Int,
      w > 0, h > 0, w <= width, h <= width,
      CGImageSourceGetStatus(source) == .statusComplete
    else { throw ArtworkFailure.invalidImage }
  }

  private func trim() {
    guard storedBytes > budget else { return }
    for (name, entry) in entries.sorted(by: { $0.value.used < $1.value.used }) {
      try? FileManager.default.removeItem(at: directory.appendingPathComponent(name))
      entries.removeValue(forKey: name)
      storedBytes -= entry.size
      if storedBytes <= budget { break }
    }
  }
}
