import AVFoundation
import Combine
import Foundation
import MediaPlayer
import Observation
import PigCompanion
import PigDomain
import PigPlayback

@MainActor @Observable final class WatchModel {
  var manifest = CompanionManifest(context: CompanionContext(revision: 0, account: nil), songs: [])
  var receipt: CompanionReceipt?
  var link: CompanionLink?
  var message: String?
  var searchResults: [Track] = []
  var loading = false
  var queue: [PlaybackOccurrence] = []
  var playback = QueuePlaybackSnapshot()
  var repeatMode: PlaybackRepeat =
    PlaybackRepeat(rawValue: UserDefaults.standard.string(forKey: "watch.repeat") ?? "off") ?? .off
  {
    didSet {
      UserDefaults.standard.set(repeatMode.rawValue, forKey: "watch.repeat")
      engine?.setRepeatMode(repeatMode)
    }
  }
  struct AlbumGroup: Identifiable {
    let id: String
    let title: String
    let artist: String
    let ids: [String]
  }
  var albums: [AlbumGroup] {
    var grouped: [String: [CompanionSong]] = [:]
    for song in manifest.songs {
      let artist = song.track.albumArtist ?? song.track.artist
      let title = song.track.album ?? "Singles"
      let key = song.track.albumId ?? (artist + "\u{0}" + title)
      grouped[key, default: []].append(song)
    }
    var result: [AlbumGroup] = []
    for (key, songs) in grouped {
      guard let first = songs.first else { continue }
      let ordered: [CompanionSong] = songs.sorted { left, right in
        let leftDisc = left.track.discNumber ?? 1
        let rightDisc = right.track.discNumber ?? 1
        if leftDisc != rightDisc { return leftDisc < rightDisc }
        let leftTrack = left.track.trackNumber ?? 0
        let rightTrack = right.track.trackNumber ?? 0
        if leftTrack != rightTrack { return leftTrack < rightTrack }
        return left.id < right.id
      }
      let ids: [String] = ordered.map { $0.id }
      result.append(
        AlbumGroup(
          id: key, title: first.track.album ?? "Singles",
          artist: first.track.albumArtist ?? first.track.artist, ids: ids))
    }
    return result.sorted { left, right in
      if left.title != right.title { return left.title < right.title }
      if left.artist != right.artist { return left.artist < right.artist }
      return left.id < right.id
    }
  }
  func finishBackgroundDelivery() async {
    await link?.finishBackgroundDelivery()
    await reload()
  }
  func retry() async {
    guard queue.indices.contains(playback.index) else { return }
    await play(queue.map { $0.track.id }, at: playback.index)
  }
  var crossfade = UserDefaults.standard.object(forKey: "watch.crossfade") as? Bool ?? true {
    didSet { UserDefaults.standard.set(crossfade, forKey: "watch.crossfade") }
  }
  var volume: Double = 0.7 { didSet { output?.volume = Float(volume) } }
  @ObservationIgnored private var archive: CompanionArchive?
  @ObservationIgnored private var output: EngineQueueOutput?
  @ObservationIgnored private var engine: RealtimeQueueSession?
  @ObservationIgnored private var notifications: [AnyCancellable] = []
  @ObservationIgnored private var playbackGeneration = 0
  @ObservationIgnored private var intent = PlaybackIntent()
  @ObservationIgnored private var listenOccurrence: UUID?
  @ObservationIgnored private var listenSeconds: Double = 0
  @ObservationIgnored private var listenReported = false
  @ObservationIgnored private var listenTick = ProcessInfo.processInfo.systemUptime
  private func measureListen(_ snapshot: QueuePlaybackSnapshot) {
    let now = ProcessInfo.processInfo.systemUptime
    let delta = min(1, max(0, now - listenTick))
    listenTick = now
    guard let id = snapshot.occurrenceID, queue.indices.contains(snapshot.index) else { return }
    if listenOccurrence != id {
      listenOccurrence = id
      listenSeconds = 0
      listenReported = false
      return
    }
    if snapshot.state == .playing { listenSeconds += delta }
    if listenSeconds >= 30, !listenReported, let archive {
      listenReported = true
      let event = ListeningEvent(
        eventId: id.uuidString, trackId: queue[snapshot.index].track.id,
        playedAt: Int(Date().timeIntervalSince1970), seconds: 30)
      Task {
        do {
          try await archive.recordListen(event)
          await flushListens()
        } catch { message = "Listening history could not be saved: " + error.localizedDescription }
      }
    }
  }
  private func flushRequests() async {
    guard let archive else { return }
    let requests = await archive.pendingRequests()
    let account = await archive.activeContext().account
    for action in ["download", "remove"] {
      let ids = requests.filter { $0.value == action }.keys.sorted()
      for offset in stride(from: 0, to: ids.count, by: 100) {
        let command = CompanionCommand(
          action, account: account, songIds: Array(ids.dropFirst(offset).prefix(100)))
        if let data = try? JSONEncoder().encode(command) { link?.message(data) }
      }
    }
  }
  private func flushListens() async {
    guard let archive else { return }
    for event in await archive.pendingListens().prefix(50) {
      let command = CompanionCommand("listen", account: manifest.context.account, listen: event)
      if let data = try? JSONEncoder().encode(command) { link?.message(data) }
    }
  }
  init() {
    do {
      let base = try FileManager.default.url(
        for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true
      ).appendingPathComponent("PigMusicWatch")
      var values = URLResourceValues()
      values.isExcludedFromBackup = true
      try FileManager.default.createDirectory(at: base, withIntermediateDirectories: true)
      var excluded = base
      try excluded.setResourceValues(values)
      archive = try CompanionArchive(directory: base.appendingPathComponent("Music"))
      link = try CompanionLink(inbox: base.appendingPathComponent("Inbox"))
      link?.onContext = { [weak self] context in await self?.contextReceived(context) }
      link?.onFile = { [weak self] file, data in await self?.fileReceived(file, data: data) }
      link?.onActivated = { [weak self] in
        await self?.reload()
        await self?.acknowledge()
        await self?.flushListens()
      }
      link?.onMessage = { [weak self] data in
        if let reply = try? JSONDecoder().decode(CompanionReply.self, from: data) {
          if let id = reply.listenId, let archive = self?.archive {
            try? await archive.acknowledgeListen(id, account: reply.account)
            await self?.flushListens()
          }
          if let message = reply.message { self?.message = message }
        }
      }
      let output = EngineQueueOutput()
      self.output = output
      output.volume = Float(volume)
      let engine = try RealtimeQueueSession(output: output, sampleRate: 44100, blockFrames: 2048)
      self.engine = engine
      engine.onUpdate = { [weak self] snapshot in
        self?.measureListen(snapshot)
        self?.playback = snapshot
        self?.updateNowPlaying()
      }
      notifications.append(
        NotificationCenter.default.publisher(for: AVAudioSession.interruptionNotification).receive(
          on: DispatchQueue.main
        ).sink {
          [weak self] notification in
          let began =
            (notification.userInfo?[AVAudioSessionInterruptionTypeKey] as? UInt)
            == AVAudioSession.InterruptionType.began.rawValue
          let resume = AVAudioSession.InterruptionOptions(
            rawValue: notification.userInfo?[AVAudioSessionInterruptionOptionKey] as? UInt ?? 0
          ).contains(.shouldResume)
          Task { @MainActor in
            guard let self else { return }
            if began {
              self.intent.beginInterruption()
              self.engine?.pause()
            } else {
              self.intent.endInterruption(shouldResume: resume)
              if self.intent.canPlay { self.activateAndResume() }
            }
          }
        })
      notifications.append(
        NotificationCenter.default.publisher(for: AVAudioSession.routeChangeNotification).receive(
          on: DispatchQueue.main
        ).sink {
          [weak self] notification in
          let removed =
            (notification.userInfo?[AVAudioSessionRouteChangeReasonKey] as? UInt)
            == AVAudioSession.RouteChangeReason.oldDeviceUnavailable.rawValue
          Task { @MainActor in
            if removed { self?.pause() } else { self?.engine?.recoverOutput() }
          }
        })
      notifications.append(
        NotificationCenter.default.publisher(for: AVAudioSession.mediaServicesWereResetNotification)
          .receive(on: DispatchQueue.main).sink { [weak self] _ in
            Task { @MainActor in
              self?.pause()
              self?.message = "Audio restarted. Tap Play to resume."
            }
          })
      MPRemoteCommandCenter.shared().playCommand.addTarget { [weak self] _ in
        Task { @MainActor in self?.activateAndResume() }
        return .success
      }
      MPRemoteCommandCenter.shared().pauseCommand.addTarget { [weak self] _ in
        Task { @MainActor in self?.pause() }
        return .success
      }
      // Headphone presses and the system Now Playing controls.
      MPRemoteCommandCenter.shared().togglePlayPauseCommand.addTarget { [weak self] _ in
        Task { @MainActor in self?.toggle() }
        return .success
      }
      MPRemoteCommandCenter.shared().changePlaybackPositionCommand.addTarget { [weak self] event in
        guard let event = event as? MPChangePlaybackPositionCommandEvent else {
          return .commandFailed
        }
        let position = event.positionTime
        Task { @MainActor in self?.seek(position) }
        return .success
      }
      MPRemoteCommandCenter.shared().nextTrackCommand.addTarget { [weak self] _ in
        Task { @MainActor in self?.next() }
        return .success
      }
      MPRemoteCommandCenter.shared().previousTrackCommand.addTarget { [weak self] _ in
        Task { @MainActor in self?.engine?.previous() }
        return .success
      }
    } catch { message = error.localizedDescription }
  }
  func reload() async {
    guard let archive else { return }
    manifest = await archive.snapshot()
    receipt = await archive.receipt()
    await flushListens()
    await flushRequests()
  }
  private func acknowledge() async {
    guard let archive else { return }
    let receipt = await archive.receipt()
    self.receipt = receipt
    do {
      try link?.publishReceipt(
        CompanionAcknowledgement(receipt: receipt, manifest: await archive.snapshot()))
    } catch { message = error.localizedDescription }
  }
  private func contextReceived(_ context: CompanionContext) async {
    guard let archive else { return }
    do {
      let old = await archive.activeContext()
      guard context.version == 1, context.revision >= old.revision,
        context.revision != old.revision || context == old
      else { return }
      if old != context { await stop() }
      try await archive.apply(context)
      await reload()
      await acknowledge()
    } catch CompanionFailure.stale {} catch { message = error.localizedDescription }
  }
  private func fileReceived(_ file: URL, data: Data) async {
    guard let archive, let envelope = try? JSONDecoder().decode(CompanionEnvelope.self, from: data)
    else {
      deleteInbox(file)
      return
    }
    let context = await archive.activeContext()
    // Context may arrive after its file.
    if envelope.context.revision > context.revision { return }
    do {
      if envelope.kind == "manifest" {
        guard envelope.context == context,
          (try file.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0) <= 2 * 1024 * 1024
        else { throw CompanionFailure.stale }
        let manifest = try JSONDecoder().decode(
          CompanionManifest.self, from: Data(contentsOf: file))
        guard manifest.context == envelope.context else { throw CompanionFailure.invalid }
        let previous = await archive.snapshot()
        let applied = await archive.receipt().manifestApplied
        if previous != manifest || !applied {
          await stop()
          try await archive.apply(manifest)
        }
      } else if envelope.kind == "audio", let ticket = envelope.file {
        // Audio can be delivered before its manifest. Keep it until that manifest arrives.
        let snapshot = await archive.snapshot()
        let applied = await archive.receipt().manifestApplied
        if snapshot.context != context || !applied,
          envelope.context == context
        {
          return
        }
        try await archive.accept(file, ticket: ticket)
      } else {
        throw CompanionFailure.invalid
      }
      deleteInbox(file)
      await reload()
      await acknowledge()
      if envelope.kind == "manifest" { await link?.recoverInbox() }
    } catch CompanionFailure.stale { deleteInbox(file) } catch {
      message = error.localizedDescription
      deleteInbox(file)
      await acknowledge()
    }
  }
  private func deleteInbox(_ file: URL) {
    try? FileManager.default.removeItem(at: file)
    try? FileManager.default.removeItem(
      at: file.deletingPathExtension().appendingPathExtension("json"))
  }
  func send(_ action: String, songIds: [String] = []) async {
    if ["download", "remove"].contains(action), let archive {
      do { try await archive.request(action, ids: songIds) } catch {
        message = error.localizedDescription
        return
      }
    }
    if action == "sync" {
      await flushRequests()
      await flushListens()
    }
    let command = CompanionCommand(action, account: manifest.context.account, songIds: songIds)
    guard let data = try? JSONEncoder().encode(command) else { return }
    if action == "remove", let archive {
      await stop()
      for id in songIds { try? await archive.removeLocal(id: id) }
      await reload()
      await acknowledge()
    }
    if link?.reachable == true {
      do {
        if let reply = try await link?.request(data),
          let value = try? JSONDecoder().decode(CompanionReply.self, from: reply)
        {
          message = value.message
        }
      } catch { message = error.localizedDescription }
    } else if ["playPause", "next", "previous"].contains(action) {
      message = "Phone remote controls require a reachable phone."
    } else {
      link?.message(data)
      message = "Request queued for your phone."
    }
  }
  func setBudget(_ gigabytes: Int) async {
    do {
      try await archive?.setBudget(Int64(gigabytes) * 1024 * 1024 * 1024)
      await reload()
      await acknowledge()
    } catch { message = error.localizedDescription }
  }
  func search(_ query: String, offset: Int = 0) async {
    guard !loading, let link, link.reachable else {
      message = "Open Pig Music on your phone to browse its library."
      return
    }
    loading = true
    defer { loading = false }
    do {
      let data = try JSONEncoder().encode(
        CompanionCommand("browse", account: manifest.context.account, query: query, offset: offset))
      let reply = try JSONDecoder().decode(CompanionReply.self, from: await link.request(data))
      if offset == 0 { searchResults = reply.songs } else { searchResults += reply.songs }
      message = reply.message
    } catch { message = error.localizedDescription }
  }
  func stop() async {
    playbackGeneration += 1
    intent.pause()
    await engine?.stopAndWait()
    queue = []
    updateNowPlaying()
  }
  func play(_ ids: [String], at index: Int = 0) async {
    guard let archive, let engine else { return }
    await stop()
    let stamp = playbackGeneration
    var items: [PlaybackOccurrence] = []
    var start = 0
    for (position, id) in ids.enumerated() {
      if let song = manifest.songs.first(where: { $0.id == id }),
        await archive.localFile(id: id) != nil
      {
        // Songs still waiting for transfer are skipped: start at the chosen
        // song, or the nearest earlier one that is on the Watch.
        if position <= index { start = items.count }
        items.append(PlaybackOccurrence(track: song.track))
      }
    }
    guard playbackGeneration == stamp, !items.isEmpty else { return }
    do {
      try await activateAudio()
      guard playbackGeneration == stamp else { return }
      queue = items
      intent.play()
      engine.replace(
        items, startingAt: start, crossfade: crossfade, repeatMode: repeatMode,
        acquire: { item in
          guard let file = await archive.localFile(id: item.track.id),
            let size = try file.resourceValues(forKeys: [.fileSizeKey]).fileSize
          else { throw CompanionFailure.stale }
          return PreparedAudioSource(file: file, byteCount: size)
        }, release: { _ in })
    } catch { message = error.localizedDescription }
  }
  private func activateAudio() async throws {
    let session = AVAudioSession.sharedInstance()
    try session.setCategory(.playback, mode: .default, policy: .longFormAudio)
    // The async form avoids a main-actor completion closure that the system
    // may call from another queue.
    guard try await session.activate(options: []) else {
      throw AudioSourceFailure.unavailable
    }
  }
  func activateAndResume() {
    intent.play()
    let stamp = playbackGeneration
    Task {
      do {
        try await activateAudio()
        guard playbackGeneration == stamp, intent.canPlay else { return }
        engine?.recoverOutput()
        engine?.resume()
      } catch { message = error.localizedDescription }
    }
  }
  func pause() {
    intent.pause()
    engine?.pause()
  }
  func toggle() { intent.wantsPlayback ? pause() : activateAndResume() }
  func next() {
    if playback.index + 1 < queue.count {
      engine?.next()
    } else if repeatMode == .all, !queue.isEmpty {
      Task { await play(queue.map { $0.track.id }) }
    } else {
      pause()
    }
  }
  func previous() { engine?.previous() }
  func seek(_ seconds: Double) { engine?.seek(seconds) }
  private func updateNowPlaying() {
    guard queue.indices.contains(playback.index) else {
      MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
      return
    }
    let track = queue[playback.index].track
    MPNowPlayingInfoCenter.default().nowPlayingInfo = [
      MPMediaItemPropertyTitle: track.title, MPMediaItemPropertyArtist: track.artist,
      MPMediaItemPropertyAlbumTitle: track.album ?? "",
      MPMediaItemPropertyPlaybackDuration: playback.duration,
      MPNowPlayingInfoPropertyElapsedPlaybackTime: playback.elapsed,
      MPNowPlayingInfoPropertyPlaybackRate: playback.state == .playing ? 1.0 : 0.0,
    ]
  }
}
