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
  @ObservationIgnored var onListen: (@MainActor (ListeningEvent) -> Void)?
  /// Called when a new song becomes current, with the songs queued after it.
  @ObservationIgnored var onUpcoming: (@MainActor ([Track]) -> Void)?
  @ObservationIgnored private var listenOccurrence: UUID?
  @ObservationIgnored private var listenSeconds: Double = 0
  @ObservationIgnored private var listenReported = false
  @ObservationIgnored private var listenTick = ProcessInfo.processInfo.systemUptime
  private func measureListen() {
    let now = ProcessInfo.processInfo.systemUptime
    let delta = min(1, max(0, now - listenTick))
    listenTick = now
    guard let item = queue.current else {
      listenOccurrence = nil
      return
    }
    if listenOccurrence != item.id {
      listenOccurrence = item.id
      listenSeconds = 0
      listenReported = false
      let next = queue.items.dropFirst(queue.index + 1).prefix(2).map(\.track)
      onUpcoming?(Array(next))
      return
    }
    if playing { listenSeconds += delta }
    if listenSeconds >= 30, !listenReported,
      item.track.serverState == nil || item.track.serverState == "in_library"
    {
      listenReported = true
      onListen?(
        ListeningEvent(
          eventId: item.id.uuidString, trackId: item.track.id,
          playedAt: Int(Date().timeIntervalSince1970), seconds: 30))
    }
  }
  @ObservationIgnored var onCheckpoint: (@MainActor (PlaybackCheckpoint) -> Void)?
  @ObservationIgnored private var checkpointTime = Date.distantPast
  @ObservationIgnored private var pendingSeek: Double = 0
  private func checkpoint(force: Bool = false) {
    guard force || Date().timeIntervalSince(checkpointTime) >= 5 else { return }
    checkpointTime = Date()
    onCheckpoint?(
      PlaybackCheckpoint(queue: queue, elapsed: pendingSeek > 0 ? pendingSeek : elapsed))
  }
  func enqueue(_ tracks: [Track], next: Bool = false) {
    guard queue.current != nil else { return }
    queue.append(tracks, next: next)
    engineQueueChanged()
  }
  func removeUpcoming(_ id: UUID) {
    queue.removeUpcoming(id)
    engineQueueChanged()
  }
  func moveUpcoming(_ id: UUID, by delta: Int) {
    queue.moveUpcoming(id, by: delta)
    engineQueueChanged()
  }
  private func engineQueueChanged() {
    if usingEngine { engine?.updateUpcoming(queue.items) }
    checkpoint(force: true)
  }
  var seamlessEnabled: Bool {
    didSet {
      guard oldValue != seamlessEnabled else { return }
      defaults.set(seamlessEnabled, forKey: "pig.playback.seamless")
      // Keep the queue and position: restart the current song in the new mode.
      if !restartingForMode, queue.current != nil { restartInCurrentMode() }
    }
  }
  @ObservationIgnored private var restartingForMode = false
  private func restartInCurrentMode() {
    guard let resolve else { return }
    let wanted = intent.wantsPlayback
    let checkpoint = PlaybackCheckpoint(
      queue: queue, elapsed: duration > 0 && elapsed >= duration ? 0 : elapsed)
    play(
      checkpoint.queue.items.map(\.track), startingAt: checkpoint.queue.index,
      autoplay: wanted, restored: checkpoint, artwork: artworkSource ?? { _ in nil },
      resolve: resolve)
  }
  var repeatMode: PlaybackRepeat = .off {
    didSet {
      defaults.set(repeatMode.rawValue, forKey: "pig.playback.repeat")
      if usingEngine { engine?.setRepeatMode(repeatMode) }
    }
  }
  private(set) var shuffled = false
  @ObservationIgnored private var originalOrder: [PlaybackOccurrence] = []
  func toggleShuffle() {
    if shuffled {
      queue.restoreUpcoming(originalOrder)
    } else {
      originalOrder = queue.items
      queue.shuffleUpcoming()
    }
    shuffled.toggle()
    engineQueueChanged()
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
    repeatMode =
      PlaybackRepeat(rawValue: defaults.string(forKey: "pig.playback.repeat") ?? "off") ?? .off
    seamlessEnabled = defaults.object(forKey: "pig.playback.seamless") as? Bool ?? true
    crossfadeEnabled = defaults.object(forKey: "pig.playback.crossfade") as? Bool ?? true
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("--seamless-demo") { seamlessEnabled = true }
    #endif
    observations.append(
      NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime).receive(on: DispatchQueue.main).sink {
        [weak self] notification in
        let identity = notification.object.map { ObjectIdentifier($0 as AnyObject) }
        Task { @MainActor in
          guard let self, !self.usingEngine, let item = self.player.currentItem,
            identity == ObjectIdentifier(item)
          else { return }
          self.finishedStreaming()
        }
      })
    observations.append(
      NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification).receive(on: DispatchQueue.main).sink {
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
      NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification).receive(on: DispatchQueue.main).sink {
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
      NotificationCenter.default.publisher(for: .AVAudioEngineConfigurationChange).receive(on: DispatchQueue.main).sink {
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
    // @Sendable keeps each handler off the main actor: the system may call it
    // from another queue, and an isolated handler would assert before its Task.
    commands.playCommand.addTarget { @Sendable [weak self] _ in
      Task { @MainActor in self?.resume() }
      return .success
    }
    commands.pauseCommand.addTarget { @Sendable [weak self] _ in
      Task { @MainActor in self?.pause() }
      return .success
    }
    // Headphone and AirPods presses arrive as a single toggle command.
    commands.togglePlayPauseCommand.addTarget { @Sendable [weak self] _ in
      Task { @MainActor in self?.toggle() }
      return .success
    }
    commands.nextTrackCommand.addTarget { @Sendable [weak self] _ in
      Task { @MainActor in self?.next() }
      return .success
    }
    commands.previousTrackCommand.addTarget { @Sendable [weak self] _ in
      Task { @MainActor in self?.previous() }
      return .success
    }
    commands.changePlaybackPositionCommand.addTarget { @Sendable [weak self] event in
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
      let session = try RealtimeQueueSession(output: output, lookaheadSeconds: 3)
      session.onUpdate = { [weak self] snapshot in self?.accept(snapshot) }
      engine = session
    }
  }
  func clearAccount() {
    onListen = nil
    onCheckpoint = nil
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
    _ tracks: [Track], startingAt: Int = 0, autoplay: Bool = true,
    restored: PlaybackCheckpoint? = nil,
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
    if autoplay { intent.play() } else { intent.pause() }
    self.resolve = resolve
    artworkSource = artwork
    if let restored {
      queue = restored.queue
    } else {
      queue.replace(tracks, startingAt: startingAt)
      shuffled = false
      originalOrder = []
    }
    pendingSeek = restored?.elapsed ?? 0
    elapsed = pendingSeek
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
        crossfade: crossfadeEnabled, repeatMode: repeatMode,
        acquire: { item in
          let url = try await resolve(item.track)
          if url.isFileURL { return try await repository.acquireLocal(item.track, file: url) }
          return try await repository.acquire(item.track, initialURL: url, resolve: resolve)
        }, release: { await repository.release($0) })
    } else {
      prepareStreaming()
    }
    if usingEngine, pendingSeek > 0 {
      engine?.seek(pendingSeek)
      pendingSeek = 0
    }
    checkpoint(force: true)
    refreshArtwork()
  }
  private func accept(_ snapshot: QueuePlaybackSnapshot) {
    guard usingEngine else { return }
    if snapshot.state != loggedState || snapshot.index != loggedIndex {
      loggedState = snapshot.state
      loggedIndex = snapshot.index
      DiagnosticsLog.shared.record(
        "playback",
        "engine \(snapshot.state) song \(snapshot.index + 1)/\(queue.items.count)"
          + (snapshot.error.map { " error=\($0)" } ?? ""))
    }
    queue.select(index: snapshot.index)
    if let id = snapshot.occurrenceID { queue.renewOccurrence(at: snapshot.index, id: id) }
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
    measureListen()
    checkpoint()
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
        if pendingSeek > 0 {
          await player.seek(to: CMTime(seconds: pendingSeek, preferredTimescale: 600))
          guard generation == stamp else { return }
          pendingSeek = 0
        }
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
        measureListen()
        checkpoint()
        publishNowPlaying()
        do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
      }
    }
  }
  @ObservationIgnored private var loggedState: QueuePlaybackState?
  @ObservationIgnored private var loggedIndex = -1
  private func interruption(began: Bool, shouldResume: Bool) {
    DiagnosticsLog.shared.record(
      "audio", began ? "interruption began" : "interruption ended, resume=\(shouldResume)")
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
    DiagnosticsLog.shared.record(
      "audio",
      "route change: \(AVAudioSession.sharedInstance().currentRoute.outputs.map(\.portType.rawValue).joined(separator: ","))"
    )
    guard usingEngine, !intent.interrupted, let state = engine?.snapshot.state,
      state == .playing || state == .paused || state == .buffering
    else { return }
    routeRecovery?.cancel()
    let stamp = generation
    routeRecovery = Task {
      do { try await Task.sleep(for: .milliseconds(250)) } catch { return }
      // Most route notifications (category changes, wake, new output on the
      // same format) leave the engine running; rebuilding then is an audible skip.
      guard generation == stamp, usingEngine, !intent.interrupted,
        engineOutput?.requiresRecovery == true
      else { return }
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
    measureListen()
    intent.pause()
    suspend()
    checkpoint(force: true)
  }
  private func finishedStreaming() {
    if repeatMode == .one {
      queue.renewOccurrence(at: queue.index, id: UUID())
      prepareStreaming()
    } else {
      next()
    }
  }
  func retry(streaming: Bool = false, fromBeginning: Bool = false) {
    guard let resolve else { return }
    let artwork = artworkSource ?? { _ in nil }
    let checkpoint = PlaybackCheckpoint(
      queue: queue,
      elapsed: fromBeginning || (duration > 0 && elapsed >= duration) ? 0 : elapsed)
    if streaming {
      restartingForMode = true
      seamlessEnabled = false
      restartingForMode = false
    }
    play(
      checkpoint.queue.items.map(\.track), startingAt: checkpoint.queue.index,
      restored: checkpoint, artwork: artwork, resolve: resolve)
  }
  func next() {
    if usingEngine {
      if queue.index + 1 < queue.items.count {
        engine?.next()
      } else if repeatMode == .all {
        queue.select(index: 0)
        retry(fromBeginning: true)
      } else {
        pause()
      }
    } else if queue.next() {
      prepareStreaming()
    } else if repeatMode == .all, !queue.items.isEmpty {
      queue.select(index: 0)
      for index in queue.items.indices { queue.renewOccurrence(at: index, id: UUID()) }
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
      currentArtwork = Self.nowPlayingArtwork(image)
      publishNowPlaying()
    }
  }
  /// MediaPlayer requests the image on its own queue. The handler must not be
  /// main-actor isolated, or Swift's isolation check stops the app.
  nonisolated private static func nowPlayingArtwork(_ image: UIImage) -> MPMediaItemArtwork {
    MPMediaItemArtwork(boundsSize: image.size) { _ in image }
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
