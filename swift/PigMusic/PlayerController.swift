import AVFoundation
import Combine
import MediaPlayer
import Observation
import PigDomain
import PigPlayback

/// Streaming alpha with an opt-in bounded engine for comparative device testing.
@MainActor @Observable final class PlayerController {
  private(set) var queue = PlaybackQueue()
  private(set) var playing = false
  private(set) var preparing = false
  private(set) var elapsed: Double = 0
  private(set) var duration: Double = 0
  var error: String?
  var seamlessEnabled: Bool {
    didSet {
      defaults.set(seamlessEnabled, forKey: "pig.playback.seamless")
      stop()
    }
  }
  var crossfadeEnabled: Bool {
    didSet { defaults.set(crossfadeEnabled, forKey: "pig.playback.crossfade") }
  }
  var wantsPlayback: Bool { intent.wantsPlayback }
  @ObservationIgnored private let defaults: UserDefaults
  @ObservationIgnored private let player = AVPlayer()
  @ObservationIgnored private var engine: RealtimeQueueSession?
  @ObservationIgnored private var engineOutput: EngineQueueOutput?
  @ObservationIgnored private var repository: PlaybackSourceRepository?
  @ObservationIgnored private var usingEngine = false
  @ObservationIgnored private var observations: [AnyCancellable] = []
  private var intent = PlaybackIntent()
  @ObservationIgnored private var clock: Task<Void, Never>?
  @ObservationIgnored private var preparation: Task<Void, Never>?
  @ObservationIgnored private var resolve: (@Sendable (Track) async throws -> URL)?
  @ObservationIgnored private var generation = 0
  @ObservationIgnored private var artworkTask: Task<Void, Never>?
  @ObservationIgnored private var artworkSource: (@MainActor (Track) async -> UIImage?)?
  @ObservationIgnored private var artworkOccurrence: UUID?
  @ObservationIgnored private var currentArtwork: MPMediaItemArtwork?
  @ObservationIgnored private var routeRecovery: Task<Void, Never>?

  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    seamlessEnabled = defaults.bool(forKey: "pig.playback.seamless")
    crossfadeEnabled = defaults.object(forKey: "pig.playback.crossfade") as? Bool ?? true
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("--seamless-demo") { seamlessEnabled = true }
    #endif
    observations.append(
      NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime).sink {
        [weak self] notification in
        let identity = notification.object.map { ObjectIdentifier($0 as AnyObject) }
        Task { @MainActor in
          guard let self, !self.usingEngine, let item = self.player.currentItem,
            identity == ObjectIdentifier(item)
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
        Task { @MainActor in self?.interruption(began: began, shouldResume: shouldResume) }
      })
    observations.append(
      NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification).sink {
        [weak self] notification in
        let reason = notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt
        Task { @MainActor in
          guard let self else { return }
          if reason == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue {
            self.pause()
          }
          if self.usingEngine { self.recoverRoute() }
        }
      })
    observations.append(
      NotificationCenter.default.publisher(for: .AVAudioEngineConfigurationChange).sink {
        [weak self] notification in
        let identity = notification.object.map { ObjectIdentifier($0 as AnyObject) }
        Task { @MainActor in
          guard let self, identity == self.engineOutput?.engineIdentity,
            self.engineOutput?.requiresRecovery == true
          else { return }
          self.recoverRoute()
        }
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

  func configureSources(directory: URL) async throws {
    stop()
    let stamp = generation
    let old = repository
    let cleanup = engine?.stop()
    await cleanup?.value
    await old?.reset()
    guard generation == stamp else { throw CancellationError() }
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    // Exclusive account root: all earlier owners have stopped; remove crash leftovers only here.
    for child in try FileManager.default.contentsOfDirectory(
      at: directory, includingPropertiesForKeys: [.isDirectoryKey, .isSymbolicLinkKey])
    where child.lastPathComponent.hasPrefix("playback-") {
      let values = try child.resourceValues(forKeys: [.isDirectoryKey, .isSymbolicLinkKey])
      if values.isDirectory == true && values.isSymbolicLink != true {
        try FileManager.default.removeItem(at: child)
      }
    }
    repository = PlaybackSourceRepository(preparer: try AudioSourcePreparer(root: directory))
    if engine == nil {
      let output = EngineQueueOutput()
      engineOutput = output
      let session = try RealtimeQueueSession(output: output)
      session.onUpdate = { [weak self] snapshot in self?.accept(snapshot) }
      engine = session
    }
  }
  func clearAccount() {
    stop()
    let old = repository
    repository = nil
    let cleanup = engine?.stop()
    Task {
      await cleanup?.value
      await old?.reset()
    }
  }
  func cachedRevisions() async -> [String: String?] { await repository?.savedRevisions() ?? [:] }
  func invalidateSources() async {
    stop()
    let old = repository
    let cleanup = engine?.stop()
    await cleanup?.value
    await old?.reset()
  }

  func play(
    _ tracks: [Track], startingAt: Int = 0,
    artwork: @escaping @MainActor (Track) async -> UIImage? = { _ in nil },
    resolve: @escaping @Sendable (Track) async throws -> URL
  ) {
    guard !tracks.isEmpty else {
      stop()
      return
    }
    preparation?.cancel()
    engine?.stop()
    clock?.cancel()
    player.pause()
    player.replaceCurrentItem(with: nil)
    generation += 1
    intent.play()
    self.resolve = resolve
    artworkSource = artwork
    queue.replace(tracks, startingAt: startingAt)
    usingEngine = seamlessEnabled
    error = nil
    if usingEngine {
      guard let repository, let engine else {
        error = "Playback storage is unavailable. Try Streaming mode."
        return
      }
      do { if intent.canPlay { try activate() } } catch {
        self.error = error.localizedDescription
        return
      }
      engine.replace(
        queue.items, startingAt: queue.index, autoplay: intent.canPlay,
        crossfade: crossfadeEnabled,
        acquire: { item in
          #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--demo") {
              let file = try await resolve(item.track)
              return try await repository.acquireLocal(item.track, file: file)
            }
          #endif
          return try await repository.acquire(item.track, resolve: resolve)
        }, release: { await repository.release($0) })
    } else {
      prepareStreaming()
    }
    refreshArtwork()
  }
  private func accept(_ snapshot: QueuePlaybackSnapshot) {
    guard usingEngine else { return }
    queue.select(index: snapshot.index)
    elapsed = snapshot.elapsed
    duration = snapshot.duration
    playing = snapshot.state == .playing
    preparing = snapshot.state == .preparing || snapshot.state == .buffering
    if snapshot.state == .failed {
      error =
        "Seamless playback could not prepare the audio. Try Streaming mode. "
        + (snapshot.error ?? "")
      intent.pause()
    } else if snapshot.state == .ended {
      intent.pause()
    }
    refreshArtwork()
    publishNowPlaying()
  }
  private func prepareStreaming() {
    generation += 1
    let stamp = generation
    preparation?.cancel()
    clock?.cancel()
    player.pause()
    player.replaceCurrentItem(with: nil)
    playing = false
    preparing = true
    elapsed = 0
    error = nil
    guard let occurrence = queue.current, let resolve else {
      stop()
      return
    }
    duration = occurrence.track.duration ?? 0
    refreshArtwork()
    publishNowPlaying()
    preparation = Task {
      do {
        let url = try await resolve(occurrence.track)
        try Task.checkCancellation()
        guard generation == stamp else { return }
        if intent.canPlay { try activate() }
        player.replaceCurrentItem(with: AVPlayerItem(url: url))
        preparing = false
        if intent.canPlay { player.play() }
        startClock()
      } catch is CancellationError {} catch {
        guard generation == stamp else { return }
        self.error = error.localizedDescription
        preparing = false
        intent.pause()
      }
    }
  }
  private func activate() throws {
    try AVAudioSession.sharedInstance().setCategory(
      .playback, mode: .default, policy: .longFormAudio)
    try AVAudioSession.sharedInstance().setActive(true)
  }
  private func startClock() {
    clock?.cancel()
    clock = Task { [weak self] in
      while !Task.isCancelled {
        guard let self else { return }
        let time = player.currentTime().seconds
        elapsed = time.isFinite ? time : 0
        let end = player.currentItem?.duration.seconds ?? 0
        if end.isFinite && end > 0 { duration = end }
        playing = player.timeControlStatus == .playing
        preparing = player.timeControlStatus == .waitingToPlayAtSpecifiedRate
        if let failed = player.currentItem?.error {
          error = failed.localizedDescription
          playing = false
          intent.pause()
        }
        publishNowPlaying()
        do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
      }
    }
  }
  private func interruption(began: Bool, shouldResume: Bool) {
    if began {
      intent.beginInterruption()
      suspend()
    } else {
      intent.endInterruption(shouldResume: shouldResume)
      if intent.canPlay {
        do { try activate() } catch {
          self.error = error.localizedDescription
          return
        }
        if usingEngine {
          engine?.recoverOutput()
          engine?.resume()
        } else {
          player.play()
        }
      }
    }
  }
  private func recoverRoute() {
    guard usingEngine, !intent.interrupted, let state = engine?.snapshot.state,
      state == .playing || state == .paused || state == .buffering
    else { return }
    routeRecovery?.cancel()
    let stamp = generation
    routeRecovery = Task {
      do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
      guard generation == stamp, usingEngine, !intent.interrupted else { return }
      do {
        if intent.canPlay { try activate() }
        engine?.recoverOutput()
      } catch { self.error = error.localizedDescription }
    }
  }
  func toggle() { intent.wantsPlayback ? pause() : resume() }
  func resume() {
    if usingEngine, engine?.snapshot.state == .ended || engine?.snapshot.state == .failed {
      if let resolve, let artworkSource {
        play(
          queue.items.map(\.track), startingAt: queue.index, artwork: artworkSource,
          resolve: resolve)
      }
      return
    }
    if !usingEngine, duration > 0, elapsed >= duration { seek(0) }
    intent.play()
    guard intent.canPlay else { return }
    do { try activate() } catch {
      self.error = error.localizedDescription
      return
    }
    if usingEngine { engine?.resume() } else if player.currentItem != nil { player.play() }
    publishNowPlaying()
  }
  private func suspend() {
    if usingEngine { engine?.pause() } else { player.pause() }
    playing = false
    publishNowPlaying()
  }
  func pause() {
    intent.pause()
    suspend()
  }
  func next() {
    if usingEngine {
      if queue.index + 1 < queue.items.count { engine?.next() } else { pause() }
    } else if queue.next() {
      prepareStreaming()
    } else {
      pause()
    }
  }
  func previous() {
    if usingEngine {
      engine?.previous()
    } else if queue.previous(elapsed: elapsed) {
      seek(0)
    } else {
      prepareStreaming()
    }
  }
  func seek(_ seconds: Double) {
    guard seconds.isFinite else { return }
    let position = min(max(0, seconds), max(0, duration))
    if usingEngine {
      engine?.seek(position)
    } else {
      player.seek(to: CMTime(seconds: position, preferredTimescale: 600))
      elapsed = position
    }
  }
  func stop() {
    generation += 1
    preparation?.cancel()
    clock?.cancel()
    routeRecovery?.cancel()
    engine?.stop()
    usingEngine = false
    player.pause()
    player.replaceCurrentItem(with: nil)
    queue.replace([])
    resolve = nil
    artworkTask?.cancel()
    artworkSource = nil
    artworkOccurrence = nil
    currentArtwork = nil
    intent = PlaybackIntent()
    playing = false
    preparing = false
    elapsed = 0
    duration = 0
    error = nil
    MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
  }
  private func refreshArtwork() {
    guard let occurrence = queue.current, artworkOccurrence != occurrence.id else { return }
    artworkTask?.cancel()
    artworkOccurrence = occurrence.id
    currentArtwork = nil
    guard let artworkSource else { return }
    artworkTask = Task {
      guard let image = await artworkSource(occurrence.track), !Task.isCancelled,
        queue.current?.id == occurrence.id
      else { return }
      currentArtwork = MPMediaItemArtwork(boundsSize: image.size) { _ in image }
      publishNowPlaying()
    }
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
