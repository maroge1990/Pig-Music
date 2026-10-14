import Foundation
import PigDomain
import Testing

struct DiagnosticsLogTests {
  private func folder() -> URL {
    FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
  }
  @Test func entriesNeverHoldLinksOrSecrets() {
    let text = DiagnosticsLog.redact(
      "stream https://music.example.au/api/v1/stream/abc?sig=123&exp=9 token=secret Bearer abc.def "
        + String(repeating: "a1", count: 20))
    #expect(text.contains("https://music.example.au/…"))
    #expect(!text.contains("sig=123"))
    #expect(!text.contains("secret"))
    #expect(!text.contains("abc.def"))
    #expect(!text.contains(String(repeating: "a1", count: 20)))
  }
  @Test func unexpectedEndIsDetectedAndBackgroundCountsAsClean() async throws {
    let root = folder()
    defer { try? FileManager.default.removeItem(at: root) }
    let first = DiagnosticsLog(directory: root)
    #expect(!first.previousRunEndedUnexpectedly)
    first.launched("Test", version: "1")
    _ = first.text()
    // Relaunch without reaching the background: the last run ended unexpectedly.
    let second = DiagnosticsLog(directory: root)
    #expect(second.previousRunEndedUnexpectedly)
    second.launched("Test", version: "1")
    second.background()
    _ = second.text()
    let third = DiagnosticsLog(directory: root)
    #expect(!third.previousRunEndedUnexpectedly)
    #expect(third.text().contains("previous run ended unexpectedly"))
  }
  @Test func logStaysBounded() {
    let root = folder()
    defer { try? FileManager.default.removeItem(at: root) }
    let log = DiagnosticsLog(directory: root, limit: 20)
    for index in 0..<100 { log.record("test", "entry \(index)") }
    let lines = log.text().split(separator: "\n")
    #expect(lines.count <= 25)
    #expect(lines.last?.hasSuffix("entry 99") == true)
  }
}
