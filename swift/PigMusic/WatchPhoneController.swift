import Foundation
import Observation
import PigBrand
import PigCompanion
import PigDomain
import PigDownloads
import SwiftUI

@MainActor @Observable final class WatchPhoneController {
  var link: CompanionLink?
  var downloads: DownloadController?
  var receipt: CompanionReceipt?
  var message: String?
  var context: CompanionContext
  @ObservationIgnored private weak var model: AppModel?
  @ObservationIgnored private let defaults: UserDefaults
  @ObservationIgnored private var namespace: String?
  @ObservationIgnored private var verified = false
  @ObservationIgnored private var poll: Task<Void, Never>?
  @ObservationIgnored private var published: CompanionManifest?
  @ObservationIgnored private var manifestURL: URL?
  @ObservationIgnored private var generation = 0
  @ObservationIgnored private var peerRevision: Int64 = 0
  @ObservationIgnored private var publishing = false
  @ObservationIgnored private var sent: [Data: Date] = [:]
  init(model: AppModel, defaults: UserDefaults) {
    self.model = model
    self.defaults = defaults
    context = CompanionContext(
      revision: Int64(defaults.integer(forKey: "pig.watch.revision")),
      account: defaults.string(forKey: "pig.watch.account"))
    do {
      let base = try FileManager.default.url(
        for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true
      ).appendingPathComponent("WatchBridge")
      link = try CompanionLink(inbox: base.appendingPathComponent("Inbox"))
      link?.onActivated = { [weak self] in await self?.publish(force: true) }
      link?.onMessage = { [weak self] data in
        if let acknowledgement = try? JSONDecoder().decode(
          CompanionAcknowledgement.self, from: data),
          acknowledgement.context.version == 1,
          acknowledgement.context.revision >= 0,
          acknowledgement.context.revision < 9_000_000_000_000_000,
          let self
        {
          peerRevision = max(peerRevision, acknowledgement.context.revision)
          if verified, context.revision < peerRevision {
            link?.cancelTransfers()
            sent = [:]
            published = nil
            receipt = nil
            advance(account: namespace)
            await publish(force: true)
          } else if let manifest = published,
            let confirmed = try? acknowledgement.receipt(for: manifest),
            confirmed.context == context
          {
            receipt = confirmed
            downloads?.budgetBytes = max(2 * 1024 * 1024 * 1024, confirmed.budgetBytes)
            await publish()
          }
        } else if let command = try? JSONDecoder().decode(CompanionCommand.self, from: data) {
          if let reply = await self?.handle(command), let encoded = try? JSONEncoder().encode(reply)
          {
            self?.link?.message(encoded)
          }
        }
      }
      link?.onRequest = { [weak self] data in
        let reply: CompanionReply
        if let command = try? JSONDecoder().decode(CompanionCommand.self, from: data), let self {
          reply = await self.handle(command)
        } else {
          reply = CompanionReply(message: "Invalid Watch request.")
        }
        return (try? JSONEncoder().encode(reply)) ?? Data()
      }
    } catch { message = error.localizedDescription }
  }
  func configure(directory: URL, namespace: String) async throws {
    generation += 1
    poll?.cancel()
    await downloads?.pause()
    self.namespace = namespace
    verified = false
    published = nil
    receipt = nil
    let archive = try DownloadArchive(directory: directory.appendingPathComponent("WatchAAC"))
    guard let service = model?.service else { return }
    downloads = DownloadController(archive: archive, source: service) { [weak self] error in
      self?.message = error.localizedDescription
    }
    downloads?.budgetBytes = max(2 * 1024 * 1024 * 1024, receipt?.budgetBytes ?? 0)
    await downloads?.reload()
    manifestURL = directory.appendingPathComponent("watch-manifest.json")
    let previousManifest = directory.appendingPathComponent(
      "watch-manifest-\(context.revision).json")
    if context.account == namespace,
      let data = try? Data(contentsOf: previousManifest),
      let old = try? JSONDecoder().decode(CompanionManifest.self, from: data),
      old.context == context
    {
      published = old
    }
    startPolling()
  }
  /// Foreground only. Without an installed Watch app there is nothing to
  /// deliver, so the bridge checks back slowly instead of every two seconds.
  private func startPolling() {
    poll?.cancel()
    guard namespace != nil else { return }
    let stamp = generation
    poll = Task { [weak self] in
      while !Task.isCancelled {
        guard let self, generation == stamp else { return }
        let paired = link?.available == true
        if paired {
          await downloads?.reload()
          await publish()
        }
        do { try await Task.sleep(for: .seconds(paired ? 2 : 30)) } catch { return }
      }
    }
  }
  func resume() {
    link?.refreshState()
    // Watch AAC preparation restarts only after the library was reconciled.
    if verified { downloads?.resume(automatic: true) }
    startPolling()
  }
  func confirmAccount() {
    if context.account != namespace || context.revision < peerRevision {
      link?.cancelTransfers()
      sent = [:]
      advance(account: namespace)
      try? link?.publish(context)
    }
  }
  func reconcile() async throws {
    guard let downloads, let store = model?.store else { return }
    let stamp = generation
    var allowed: [String: String?] = [:]
    for record in downloads.records {
      if let track = try await store.track(id: record.id) {
        allowed.updateValue(track.sourceRevision, forKey: record.id)
      }
    }
    guard generation == stamp else { return }
    await downloads.reconcile(allowed)
    guard generation == stamp else { return }
    verified = true
    await followPlaylists()
    guard generation == stamp else { return }
    downloads.resume()
    await publish()
  }
  var supported: Bool { link?.supported == true }
  func enqueue(_ tracks: [Track], origin: DownloadOrigin = .direct) async {
    guard supported else {
      message = "Watch downloads are managed by its paired iPhone."
      return
    }
    guard verified, let downloads else {
      message = "Connect and refresh your phone library first."
      return
    }
    guard
      downloads.records.count
        + Set(tracks.map(\.id)).subtracting(Set(downloads.records.map(\.id))).count
        <= 1000
    else {
      message = "Choose up to 1,000 songs for your Watch library."
      return
    }
    let stamp = generation
    do {
      var personal: [Track] = []
      for id in Set(tracks.map(\.id)) {
        if let track = try await model?.store?.track(id: id) { personal.append(track) }
      }
      guard generation == stamp else { return }
      guard !personal.isEmpty else {
        message = "Add these songs to your library before downloading them to Watch."
        return
      }
      try await downloads.enqueue(personal, quality: "aac", origin: origin)
      if personal.count < Set(tracks.map(\.id)).count {
        message =
          "Only songs in your library can be sent to Watch. Add or request the remaining songs first."
      }
      await publish()
    } catch { message = error.localizedDescription }
  }
  func remove(_ id: String) async {
    await downloads?.remove(id: id)
    await publish()
  }
  /// Removes an album's or playlist's claim; songs another one needs stay.
  func release(_ ids: [String], origin: DownloadOrigin) async {
    await downloads?.release(ids: ids, origin: origin)
    await publish()
  }
  /// Playlists sent to the Watch follow later changes: new songs are added,
  /// removed songs are released, and a deleted playlist leaves the Watch.
  /// Runs only from `reconcile`, after a successful sync, so an empty list means
  /// the person has no playlists left and the last one's songs are released.
  private func followPlaylists() async {
    guard let downloads, let model, let store = model.store else { return }
    var sentPlaylists: [String: (name: String?, ids: Set<String>)] = [:]
    for record in downloads.records {
      for origin in record.effectiveOrigins {
        guard let id = origin.playlistId else { continue }
        sentPlaylists[id, default: (origin.playlistName, [])].ids.insert(record.id)
      }
    }
    for (id, sent) in sentPlaylists {
      guard let playlist = model.playlists.first(where: { $0.id == id }) else {
        await downloads.release(
          ids: Array(sent.ids), origin: DownloadOrigin(playlistId: id, playlistName: sent.name))
        continue
      }
      guard let entries = playlist.entries else { continue }
      let origin = DownloadOrigin(playlistId: id, playlistName: playlist.name)
      let wanted = Set(entries.compactMap { $0.savedId ?? $0.savedTrack?.id })
      let gone = sent.ids.subtracting(wanted)
      if !gone.isEmpty { await downloads.release(ids: Array(gone), origin: origin) }
      // New songs, or every song when the playlist was renamed.
      let refresh = playlist.name == sent.name ? wanted.subtracting(sent.ids) : wanted
      let room = 1000 - downloads.records.count
      var tracks: [Track] = []
      for songId in refresh.sorted() {
        guard tracks.count < max(0, room) || sent.ids.contains(songId) else { continue }
        if let track = try? await store.track(id: songId) { tracks.append(track) }
      }
      if !tracks.isEmpty { try? await downloads.enqueue(tracks, quality: "aac", origin: origin) }
    }
  }
  func pause() async {
    poll?.cancel()
    poll = nil
    await downloads?.pause()
  }
  func disconnect() {
    generation += 1
    poll?.cancel()
    poll = nil
    if let downloads { Task { await downloads.clear() } }
    downloads = nil
    verified = false
    namespace = nil
    receipt = nil
    published = nil
    sent = [:]
    link?.cancelTransfers()
    advance(account: nil)
    try? link?.publish(context)
  }
  private func advance(account: String?) {
    context = CompanionContext(revision: max(context.revision, peerRevision) + 1, account: account)
    defaults.set(context.revision, forKey: "pig.watch.revision")
    defaults.set(account, forKey: "pig.watch.account")
  }
  func publish(force: Bool = false) async {
    guard !publishing else { return }
    guard verified, let downloads, let namespace, let baseManifestURL = manifestURL else {
      if context.account == nil { try? link?.publish(context) }
      return
    }
    if force { sent = [:] }
    publishing = true
    defer { publishing = false }
    let stamp = generation
    var songs: [CompanionSong] = []
    var files: [String: URL] = [:]
    for record in downloads.records where record.state == "ready" {
      if let checksum = record.checksum, let file = await downloads.archive.localFile(record.track)
      {
        songs.append(CompanionSong(track: record.track, checksum: checksum, bytes: record.total))
        files[record.id] = file
      }
    }
    guard generation == stamp else { return }
    songs.sort { $0.id < $1.id }
    let ids = Set(songs.map(\.id))
    var remainingOccurrences = 10000
    // Only playlists sent to the Watch appear there.
    let sentPlaylists = Set(
      downloads.records.flatMap { $0.effectiveOrigins.compactMap(\.playlistId) })
    let collections = (model?.playlists ?? []).filter { sentPlaylists.contains($0.id) }.prefix(200)
      .map { playlist in
      let selected = (playlist.entries ?? []).compactMap { $0.savedId ?? $0.savedTrack?.id }.filter
      { ids.contains($0) }
      let songIds = Array(selected.prefix(remainingOccurrences))
      remainingOccurrences -= songIds.count
      return CompanionCollection(
        id: playlist.id, name: playlist.name, songIds: songIds,
        favourites: playlist.favourites == true)
    }
    // A batch produces one manifest once AAC preparation finishes; removals still publish immediately.
    if downloads.running, let published, published.context.account == namespace,
      published.songs.allSatisfy({ old in songs.contains(old) }),
      published.collections == collections
    {
      return
    }
    var manifestURL = baseManifestURL.deletingLastPathComponent().appendingPathComponent(
      "watch-manifest-\(context.revision).json")
    var next = CompanionManifest(context: context, songs: songs, collections: collections)
    if context.account != namespace || published?.songs != songs
      || published?.collections != collections
    {
      link?.cancelTransfers()
      sent = [:]
      advance(account: namespace)
      next.context = context
      manifestURL = baseManifestURL.deletingLastPathComponent().appendingPathComponent(
        "watch-manifest-\(context.revision).json")
      receipt = nil
      published = next
      do {
        let data = try JSONEncoder().encode(next)
        guard data.count <= 2 * 1024 * 1024 else {
          published = nil
          message = "Watch metadata is too large. Choose fewer songs or shorter playlist names."
          return
        }
        try data.write(to: manifestURL, options: .atomic)
      } catch {
        published = nil
        message = error.localizedDescription
        return
      }
    }
    do { try link?.publish(context) } catch {
      message = error.localizedDescription
      return
    }
    if force || receipt?.context != context || receipt?.manifestApplied != true {
      let metadata = CompanionEnvelope(kind: "manifest", context: context)
      if let data = try? JSONEncoder().encode(metadata),
        sent[data].map({ Date().timeIntervalSince($0) > 600 }) ?? true,
        !(link?.outstanding.contains(data) ?? false)
      {
        link?.transfer(manifestURL, metadata: data)
        sent[data] = Date()
      }
    }
    let retained = Set(
      (link?.outstanding ?? []).compactMap {
        (try? JSONDecoder().decode(CompanionEnvelope.self, from: $0))?.context.revision
      })
    for file
      in (try? FileManager.default.contentsOfDirectory(
        at: baseManifestURL.deletingLastPathComponent(), includingPropertiesForKeys: nil)) ?? []
    where file.lastPathComponent.hasPrefix("watch-manifest-") && file != manifestURL {
      let revision = Int64(
        file.deletingPathExtension().lastPathComponent.replacingOccurrences(
          of: "watch-manifest-", with: ""))
      if let revision, !retained.contains(revision) {
        try? FileManager.default.removeItem(at: file)
      }
    }
    // Do not send audio until the Watch has applied this manifest and acknowledged its budget.
    guard let receipt, receipt.context == context, receipt.manifestApplied else { return }
    var remaining = receipt.budgetBytes - receipt.usedBytes
    for song in songs where receipt.ready[song.id] != song.checksum {
      guard song.bytes <= remaining else {
        message = "Watch storage budget is full. Remove Watch songs before adding more."
        continue
      }
      remaining -= song.bytes
      let ticket = CompanionFile(context: context, songId: song.id, checksum: song.checksum)
      let envelope = CompanionEnvelope(kind: "audio", context: context, file: ticket)
      if let file = files[song.id], let data = try? JSONEncoder().encode(envelope),
        sent[data].map({ Date().timeIntervalSince($0) > 600 }) ?? true,
        !(link?.outstanding.contains(data) ?? false)
      {
        link?.transfer(file, metadata: data)
        sent[data] = Date()
      }
    }
  }
  private func handle(_ command: CompanionCommand) async -> CompanionReply {
    guard verified, command.account == context.account, let model, let store = model.store else {
      return CompanionReply(message: "Refresh the library on your phone first.")
    }
    let stamp = generation
    do {
      switch command.action {
      case "listen":
        guard let event = command.listen, UUID(uuidString: event.id) != nil,
          event.seconds == 30, event.playedAt > Int(Date().timeIntervalSince1970) - 30 * 86400,
          event.playedAt <= Int(Date().timeIntervalSince1970) + 300,
          try await store.track(id: event.trackId) != nil
        else {
          return CompanionReply(listenId: command.listen?.id, account: command.account)
        }
        try await store.recordListen(event)
        await model.flushHistory()
        return CompanionReply(listenId: event.id, account: command.account)
      case "download":
        guard command.songIds.count <= 100 else {
          return CompanionReply(message: "Choose up to 100 songs at a time.")
        }
        var tracks: [Track] = []
        for id in command.songIds {
          if let track = try await store.track(id: id) { tracks.append(track) }
        }
        guard generation == stamp, verified, command.account == context.account else {
          return CompanionReply(message: "The phone account changed. Retry after syncing.")
        }
        await enqueue(tracks)
        return CompanionReply(
          message: "Queued on your phone. AAC files transfer when both devices are available.")
      case "remove":
        for id in command.songIds.prefix(100) {
          guard generation == stamp, command.account == context.account else {
            return CompanionReply(message: "The phone account changed.")
          }
          await remove(id)
        }
      case "playPause": model.player.toggle()
      case "next": model.player.next()
      case "previous": model.player.previous()
      case "sync": await publish(force: true)
      default: return CompanionReply(message: "Unsupported Watch command.")
      }
      return CompanionReply()
    } catch { return CompanionReply(message: error.localizedDescription) }
  }
}

/// Music sent to Apple Watch: transfers first, then what is on the Watch grouped
/// by album and playlist. Music is chosen from album, artist, playlist and song pages.
struct WatchDownloadsView: View {
  let model: AppModel
  @State private var removing: DeviceGroup?
  var body: some View {
    List {
      if let watch = model.watch {
        let records = watch.downloads?.records ?? []
        let delivered = records.filter { onWatch($0, watch: watch) }
        let transfers = records.filter { !onWatch($0, watch: watch) || $0.cleared != true }
        if records.isEmpty {
          Text("Nothing sent yet. Use Send to Apple Watch on an album, artist, playlist or song.")
            .foregroundStyle(.secondary)
        }
        if !transfers.isEmpty {
          Section("Transfers") {
            ForEach(transfers) { record in
              HStack(spacing: 12) {
                ArtworkThumb(
                  model: model, source: record.track.artworkSource, title: record.track.title)
                VStack(alignment: .leading, spacing: 2) {
                  Text(record.track.title).lineLimit(1)
                  Text(record.track.artist).font(PigType.caption).foregroundStyle(.secondary)
                    .lineLimit(1)
                }
                Spacer(minLength: 0)
                mark(record, watch: watch).frame(width: 28, height: 28)
              }
              .accessibilityElement(children: .combine)
              .accessibilityValue(status(record, watch: watch))
              .swipeActions {
                if !onWatch(record, watch: watch) {
                  Button("Cancel", role: .destructive) { Task { await watch.remove(record.id) } }
                }
              }
            }
          }
        }
        let groups = DeviceGroup.build(delivered)
        if !groups.isEmpty {
          Section("On Apple Watch") {
            ForEach(groups) { group in
              DisclosureGroup {
                ForEach(group.records) { record in
                  HStack {
                    Text(record.track.title).lineLimit(1)
                    Spacer(minLength: 0)
                    RemoveButton(label: "Remove \(record.track.title) from Apple Watch") {
                      Task { await watch.release([record.id], origin: group.origin) }
                    }
                  }
                }
              } label: {
                HStack(spacing: 12) {
                  ArtworkThumb(model: model, source: group.artwork, title: group.title, size: 44)
                  VStack(alignment: .leading, spacing: 2) {
                    Text(group.title).lineLimit(1)
                    Text(group.caption).font(PigType.caption).foregroundStyle(.secondary)
                      .lineLimit(1)
                  }
                  Spacer(minLength: 0)
                  RemoveButton(label: "Remove \(group.title) from Apple Watch") { removing = group }
                }
              }
            }
          }
        }
        Section("Status") {
          Text(
            watch.link?.available != true
              ? "Install Pig Music on your paired Watch"
              : watch.link?.reachable == true ? "Watch reachable" : "Transfers wait for the Watch")
          if let receipt = watch.receipt {
            Text(
              "\(receipt.ready.count) songs on Watch · \(ByteCountFormatter.string(fromByteCount: receipt.usedBytes, countStyle: .file))"
            )
          }
          Button("Retry Watch transfers") { Task { await watch.publish(force: true) } }
          if let error = watch.message ?? watch.link?.error {
            Text(error).foregroundStyle(Color("PigDanger"))
          }
          Text(
            "Playlists sent to the Watch update when they change. AAC copies also use storage on this iPhone while on the Watch. Transfers are scheduled by the system."
          ).font(PigType.footnote)
        }
      }
    }
    .pigCanvas().navigationTitle("Apple Watch")
    .toolbar {
      if let watch = model.watch {
        let records = watch.downloads?.records ?? []
        Button("Clear finished") {
          Task {
            await watch.downloads?.clearFinished(
              ids: Set(records.filter { onWatch($0, watch: watch) }.map(\.id)))
          }
        }.disabled(!records.contains { onWatch($0, watch: watch) && $0.cleared != true })
      }
    }
    .confirmationDialog(
      removing.map { "Remove \($0.title) from Apple Watch?" } ?? "",
      isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
      titleVisibility: .visible
    ) {
      if let group = removing, let watch = model.watch {
        Button("Remove", role: .destructive) {
          Task { await watch.release(group.records.map(\.id), origin: group.origin) }
        }
      }
    } message: {
      Text("Songs also in another album or playlist on the Watch stay there.")
    }
  }
  private func onWatch(_ record: DownloadRecord, watch: WatchPhoneController) -> Bool {
    record.checksum != nil && watch.receipt?.ready[record.id] == record.checksum
  }
  @ViewBuilder private func mark(_ record: DownloadRecord, watch: WatchPhoneController)
    -> some View
  {
    if onWatch(record, watch: watch) {
      Image(systemName: "checkmark.circle.fill").foregroundStyle(Color.accentColor)
    } else if record.state == "failed" {
      Button {
        Task { await watch.enqueue([record.track], origin: record.effectiveOrigins.last ?? .direct) }
      } label: {
        Image(systemName: "exclamationmark.arrow.circlepath").foregroundStyle(Color("PigDanger"))
      }.buttonStyle(.borderless).accessibilityLabel("Retry")
    } else if record.state == "ready" {
      Image(systemName: "applewatch.radiowaves.left.and.right").foregroundStyle(.secondary)
    } else {
      ProgressView().controlSize(.small)
    }
  }
  private func status(_ record: DownloadRecord, watch: WatchPhoneController) -> String {
    if onWatch(record, watch: watch) { return "On Watch" }
    return switch record.state {
    case "ready": "Waiting for Watch"
    case "failed": "Failed"
    default: "Preparing"
    }
  }
}
