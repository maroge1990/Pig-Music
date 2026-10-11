import AVFoundation
import Combine
import MediaPlayer
import Observation
import PigDomain
import PigPlayback

/// Connected-alpha player. Transition architecture is validated separately before replacement.
@MainActor @Observable final class PlayerController {
  private(set) var queue = PlaybackQueue()
  private(set) var playing = false
  private(set) var elapsed: Double = 0
  private(set) var duration: Double = 0
  var error: String?
  @ObservationIgnored private let player = AVPlayer()
  @ObservationIgnored private var observations: [AnyCancellable] = []
  @ObservationIgnored private var interruptionWasPlaying = false
  @ObservationIgnored private var clock: Task<Void, Never>?
  @ObservationIgnored private var preparation: Task<Void, Never>?
  @ObservationIgnored private var resolve: (@Sendable (Track) async throws -> URL)?
  @ObservationIgnored private var generation = 0
  @ObservationIgnored private var artworkTask: Task<Void, Never>?
  @ObservationIgnored private var artworkSource: (@MainActor (Track) async -> UIImage?)?
  @ObservationIgnored private var currentArtwork: MPMediaItemArtwork?

  init() {
    observations.append(
      NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime).sink {
        [weak self] notification in
        let identity = notification.object.map { ObjectIdentifier($0 as AnyObject) }
        Task { @MainActor in
          guard let self, let item = self.player.currentItem, identity == ObjectIdentifier(item)
          else { return }
          self.next()
        }
      })
    observations.append(
      NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification).sink {
        [weak self] notification in
        let began =
          (notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt)
          == AVAudioSession.InterruptionType.began.rawValue
        let options = notification.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
        let shouldResume = AVAudioSession.InterruptionOptions(rawValue: options).contains(
          .shouldResume)
        Task { @MainActor in
          guard let self else { return }
          if began {
            self.interruptionWasPlaying = self.playing
            self.pause()
          } else if shouldResume && self.interruptionWasPlaying {
            self.resume()
            self.interruptionWasPlaying = false
          }
        }
      })
    observations.append(
      NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification).sink {
        [weak self] notification in
        let unplugged =
          (notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt)
          == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue
        if unplugged { Task { @MainActor in self?.pause() } }
      })
    let commands = MPRemoteCommandCenter.shared()
    commands.playCommand.addTarget { [weak self] _ in
      Task { @MainActor in self?.resume() }
      return .success
    }
    commands.pauseCommand.addTarget { [weak self] _ in
      Task { @MainActor in self?.pause() }
      return .success
    }
    commands.nextTrackCommand.addTarget { [weak self] _ in
      Task { @MainActor in self?.next() }
      return .success
    }
    commands.previousTrackCommand.addTarget { [weak self] _ in
      Task { @MainActor in self?.previous() }
      return .success
    }
    commands.changePlaybackPositionCommand.addTarget { [weak self] event in
      guard let event = event as? MPChangePlaybackPositionCommandEvent else {
        return .commandFailed
      }
      let position = event.positionTime
      Task { @MainActor in self?.seek(position) }
      return .success
    }
  }
  func play(
    _ tracks: [Track], startingAt: Int = 0,
    artwork: @escaping @MainActor (Track) async -> UIImage? = { _ in nil },
    resolve: @escaping @Sendable (Track) async throws -> URL
  ) {
    self.resolve = resolve
    artworkSource = artwork
    queue.replace(tracks, startingAt: startingAt)
    prepare()
  }
  private func prepare() {
    generation += 1
    let stamp = generation
    preparation?.cancel()
    clock?.cancel()
    artworkTask?.cancel()
    currentArtwork = nil
    player.pause()
    player.replaceCurrentItem(with: nil)
    playing = false
    elapsed = 0
    error = nil
    guard let occurrence = queue.current, let resolve else {
      stop()
      return
    }
    duration = occurrence.track.duration ?? 0
    publishNowPlaying()
    if let artworkSource {
      artworkTask = Task {
        guard let image = await artworkSource(occurrence.track),
          !Task.isCancelled, generation == stamp
        else { return }
        currentArtwork = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
        publishNowPlaying()
      }
    }
    preparation = Task {
      do {
        let url = try await resolve(occurrence.track)
        try Task.checkCancellation()
        guard generation == stamp else { return }
        try AVAudioSession.sharedInstance().setCategory(
          .playback, mode: .default, policy: .longFormAudio)
        try AVAudioSession.sharedInstance().setActive(true)
        player.replaceCurrentItem(with: AVPlayerItem(url: url))
        resume()
        startClock()
      } catch is CancellationError {} catch {
        guard generation == stamp else { return }
        self.error = error.localizedDescription
      }
    }
  }
  private func startClock() {
    clock?.cancel()
    clock = Task {
      while !Task.isCancelled {
        let time = player.currentTime().seconds
        elapsed = time.isFinite ? time : 0
        let end = player.currentItem?.duration.seconds ?? 0
        if end.isFinite && end > 0 { duration = end }
        playing = player.timeControlStatus == .playing
        if let failed = player.currentItem?.error {
          error = failed.localizedDescription
          playing = false
        }
        publishNowPlaying()
        try? await Task.sleep(for: .milliseconds(500))
      }
    }
  }
  func toggle() { playing ? pause() : resume() }
  func resume() {
    guard player.currentItem != nil else { return }
    player.play()
    playing = true
    publishNowPlaying()
  }
  func pause() {
    player.pause()
    playing = false
    publishNowPlaying()
  }
  func next() { if queue.next() { prepare() } else { pause() } }
  func previous() { if queue.previous(elapsed: elapsed) { seek(0) } else { prepare() } }
  func seek(_ seconds: Double) {
    player.seek(to: CMTime(seconds: max(0, seconds), preferredTimescale: 600))
    elapsed = max(0, seconds)
  }
  func stop() {
    generation += 1
    preparation?.cancel()
    clock?.cancel()
    player.pause()
    player.replaceCurrentItem(with: nil)
    queue.replace([])
    resolve = nil
    artworkTask?.cancel()
    artworkSource = nil
    currentArtwork = nil
    playing = false
    elapsed = 0
    error = nil
    MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
  }
  private func publishNowPlaying() {
    guard let song = queue.current?.track else { return }
    var information: [String: Any] = [
      MPMediaItemPropertyTitle: song.title, MPMediaItemPropertyArtist: song.artist,
      MPMediaItemPropertyAlbumTitle: song.album ?? "",
      MPMediaItemPropertyPlaybackDuration: duration,
      MPNowPlayingInfoPropertyElapsedPlaybackTime: elapsed,
      MPNowPlayingInfoPropertyPlaybackRate: playing ? 1.0 : 0.0,
    ]
    if let currentArtwork { information[MPMediaItemPropertyArtwork] = currentArtwork }
    MPNowPlayingInfoCenter.default().nowPlayingInfo = information
  }
}
