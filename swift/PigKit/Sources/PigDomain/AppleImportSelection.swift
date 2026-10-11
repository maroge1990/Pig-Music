import Foundation

public struct AppleImportPlaylist: Sendable, Identifiable {
  public let id: Int
  public let name: String
  public let songs: Int
}

/// Filters the original plist without changing persistent identifiers or repeated occurrences.
public struct AppleImportSelection: Sendable {
  private let data: Data
  public let playlists: [AppleImportPlaylist]
  public init(data: Data) throws {
    guard !data.isEmpty, data.count <= 20_000_000 else { throw CocoaError(.fileReadTooLarge) }
    let root = try Self.root(data)
    guard root["Tracks"] is [String: Any] else { throw CocoaError(.fileReadCorruptFile) }
    self.data = data
    playlists = (root["Playlists"] as? [[String: Any]] ?? []).enumerated().compactMap {
      index, item in
      guard let name = item["Name"] as? String, !name.isEmpty,
        item["Master"] as? Bool != true, item["Folder"] as? Bool != true
      else { return nil }
      return AppleImportPlaylist(
        id: index, name: name, songs: (item["Playlist Items"] as? [[String: Any]] ?? []).count)
    }
  }
  public func export(selected: Set<Int>, includeOtherTracks: Bool = false) throws -> Data {
    guard !selected.isEmpty, selected.isSubset(of: Set(playlists.map(\.id))) else {
      throw CocoaError(.fileReadCorruptFile)
    }
    var root = try Self.root(data)
    let all = root["Playlists"] as? [[String: Any]] ?? []
    let chosen = all.enumerated().filter { selected.contains($0.offset) }.map(\.element)
    root["Playlists"] = chosen
    if !includeOtherTracks {
      let ids = Set(
        chosen.flatMap { $0["Playlist Items"] as? [[String: Any]] ?? [] }.compactMap {
          ($0["Track ID"] as? NSNumber)?.stringValue
        })
      let tracks = root["Tracks"] as? [String: Any] ?? [:]
      root["Tracks"] = tracks.filter { key, value in
        ids.contains(key)
          || ((value as? [String: Any])?["Track ID"] as? NSNumber).map {
            ids.contains($0.stringValue)
          } == true
      }
    }
    return try PropertyListSerialization.data(fromPropertyList: root, format: .xml, options: 0)
  }
  private static func root(_ data: Data) throws -> [String: Any] {
    guard
      let root = try PropertyListSerialization.propertyList(from: data, options: [], format: nil)
        as? [String: Any]
    else { throw CocoaError(.fileReadCorruptFile) }
    return root
  }
}
