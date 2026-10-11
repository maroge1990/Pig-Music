/// User intent survives preparation and interruption suspension independently of output state.
public struct PlaybackIntent: Sendable, Equatable {
  public private(set) var wantsPlayback = false
  public private(set) var interrupted = false
  public var canPlay: Bool { wantsPlayback && !interrupted }
  public init() {}
  public mutating func play() { wantsPlayback = true }
  public mutating func pause() { wantsPlayback = false }
  public mutating func beginInterruption() { interrupted = true }
  public mutating func endInterruption(shouldResume: Bool) {
    interrupted = false
    if !shouldResume { wantsPlayback = false }
  }
}
