import Foundation
import PigDomain
import Testing

struct AppleImportSelectionTests {
  @Test func selectionPreservesIdentifiersAndRepeatsWithoutImportingUnselectedMusic() throws {
    let source: [String: Any] = [
      "Library Persistent ID": "library",
      "Tracks": [
        "1": ["Track ID": 1, "Name": "First", "Persistent ID": "one"],
        "2": ["Track ID": 2, "Name": "Second"],
      ],
      "Playlists": [
        ["Name": "All", "Master": true],
        [
          "Name": "Chosen", "Playlist Persistent ID": "chosen",
          "Playlist Items": [["Track ID": 1], ["Track ID": 1]],
        ],
        ["Name": "Other", "Playlist Items": [["Track ID": 2]]],
      ],
    ]
    let data = try PropertyListSerialization.data(
      fromPropertyList: source, format: .xml, options: 0)
    let selection = try AppleImportSelection(data: data)
    #expect(selection.playlists.map(\.id) == [1, 2])
    let exported = try selection.export(selected: [1])
    let root = try #require(
      try PropertyListSerialization.propertyList(from: exported, format: nil) as? [String: Any])
    #expect(root["Library Persistent ID"] as? String == "library")
    #expect((root["Tracks"] as? [String: Any])?.count == 1)
    let playlists = try #require(root["Playlists"] as? [[String: Any]])
    #expect(playlists.count == 1)
    #expect(playlists[0]["Playlist Persistent ID"] as? String == "chosen")
    #expect((playlists[0]["Playlist Items"] as? [[String: Any]])?.count == 2)
    #expect(throws: (any Error).self) { try selection.export(selected: [0]) }
    let entire = try selection.export(selected: [1], includeOtherTracks: true)
    #expect(
      ((try PropertyListSerialization.propertyList(from: entire, format: nil) as? [String: Any])?[
        "Tracks"] as? [String: Any])?.count == 2)
  }
}
