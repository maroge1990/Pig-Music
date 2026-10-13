import CryptoKit
import Foundation
import Observation
import PigAPI
import PigDomain
import PigDownloads
import PigPlayback
import PigStore
import PigSync
import UIKit

@MainActor @Observable final class AppModel {
  struct Connection: Codable {
    var server: String
    var person: Person
  }
  var watch: WatchPhoneController?
  var downloads: DownloadController?
  var preferences = AccountPreferences()
  var person: Person?
  var server = ""
  var busy = false
  var syncing = false
  var message: String?
  var songSort: LibrarySort = .title
  var albumSort: LibrarySort = .title
  var artistSort: LibrarySort = .title
  var songs: [Track] = []
  var albums: [Album] = []
  var artists: [Artist] = []
  var playlists: [Playlist] = []
  var homeContent: [HomeSection: HomeContent] = [:]
  var homeErrors: [HomeSection: String] = [:]
  var homeLoading: Set<HomeSection> = []
  var searchSession: SearchSession?
  var actionTrack: Track?
  /// Music requests the server is still getting, from the requests page summary.
  var serverActiveRequests = 0
  var pendingEdits: [PendingMutation] = []
  @ObservationIgnored private var flushingEdits = false
  var mutationActive = false
  var canMutate: Bool { service != nil && !busy && !syncing && !mutationActive }
  var songCount = 0
  var albumCount = 0
  var artistCount = 0
  /// Album category shown in Library ("album", "musical", "soundtrack", "compilation").
  var albumCategory = "album"
  var albumCategoryCounts: [String: Int] = [:]
  var loadingMore = false
  @ObservationIgnored private var flushingHistory = false
  let player = PlayerController()
  var artworkNamespace = ""
  var artworkRefresh = 0
  @ObservationIgnored private var artworkCache: ArtworkCache?
  @ObservationIgnored private let artworkMemory = NSCache<NSString, UIImage>()
  @ObservationIgnored private var artistCovers: [String: String?] = [:]
  @ObservationIgnored private var catalogueMemory: [String: any Sendable] = [:]
  @ObservationIgnored private(set) var service: NativeService?
  @ObservationIgnored private(set) var store: LibraryStore?
  @ObservationIgnored private var sync: SyncCoordinator?
  @ObservationIgnored private var generation = 0
  @ObservationIgnored private var restoring = false
  @ObservationIgnored private var liveTask: Task<Void, Never>?
  @ObservationIgnored private var activeScene = true
  @ObservationIgnored private let defaults: UserDefaults
  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
    watch = WatchPhoneController(model: self, defaults: defaults)
    artworkMemory.countLimit = 128
    artworkMemory.totalCostLimit = 24 * 1024 * 1024
  }

  func restore() async {
    guard !restoring, !busy, person == nil else { return }
    restoring = true
    busy = true
    defer {
      restoring = false
      busy = false
    }
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("--demo") {
        await loadDemo()
        return
      }
    #endif
    guard let data = defaults.data(forKey: "pig.connection"),
      let connection = try? JSONDecoder().decode(Connection.self, from: data)
    else { return }
    server = connection.server
    do {
      let vault = TokenVault(account: connection.server)
      guard try await vault.read() != nil else {
        defaults.removeObject(forKey: "pig.connection")
        return
      }
      let service = try NativeService(server: connection.server, vault: vault)
      try await attach(connection.person, service: service)
      await refresh()
      startLiveUpdates()
    } catch { message = error.localizedDescription }
  }
  func sceneActive(_ active: Bool) async {
    activeScene = active
    liveTask?.cancel()
    liveTask = nil
    if !active {
      await downloads?.suspendPreparation()
      await watch?.pause()
      return
    }
    downloads?.resumePreparation()
    watch?.resume()
    await refresh()
    startLiveUpdates()
  }
  private func startLiveUpdates() {
    guard activeScene, liveTask == nil, let service else { return }
    let stamp = generation
    liveTask = Task { [weak self] in
      var delay = 1
      while !Task.isCancelled {
        guard let self, generation == stamp else { return }
        do {
          let events = try await service.events()
          for try await event in events {
            guard generation == stamp, !Task.isCancelled else { return }
            delay = 1
            if event == "revoked" {
              revoked(generation: stamp)
              return
            }
            if event == "revision" { await refresh() }
          }
        } catch NativeFailure.authentication {
          revoked(generation: stamp)
          return
        } catch is CancellationError { return } catch {
          // Cached browsing and manual refresh remain available.
        }
        guard generation == stamp, !Task.isCancelled else { return }
        do { try await Task.sleep(for: .seconds(delay)) } catch { return }
        delay = min(30, delay * 2)
        await refresh()
      }
    }
  }
  func saveDownloadBudget(_ bytes: Int64) {
    defaults.set(Int(bytes), forKey: "pig.download-budget:" + artworkNamespace)
  }
  func download(
    _ tracks: [Track], quality: String = "original", origin: DownloadOrigin = .direct
  ) async {
    guard let downloads else { return }
    do {
      try await downloads.enqueue(tracks, quality: quality, origin: origin)
      let stamp = generation
      let covers = Set(tracks.compactMap(\.coverSha))
      for sha in covers {
        guard generation == stamp, !Task.isCancelled else { return }
        _ = await artwork(sha: sha, width: 512)
        _ = await artwork(sha: sha, width: 256)
      }
    } catch { message = error.localizedDescription }
  }
  func cachePreferences() async { try? await store?.cache(preferences, key: "preferences") }
  func join(invitation: String, password: String) async {
    guard !busy else { return }
    busy = true
    message = nil
    defer { busy = false }
    do {
      let invite: Invite
      if invitation.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("https://") {
        invite = try Invite.parse(invitation)
      } else {
        let code = invitation.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        guard Invite.codeLengths.contains(code.count),
          code.allSatisfy({ Invite.codeAlphabet.contains($0) })
        else {
          throw NativeFailure.unavailable("Enter a valid invitation code or full invitation link.")
        }
        invite = Invite(server: try ServerAddress.validate(server), code: code)
      }
      let saved = try await Onboarding().join(
        invite, password: password, deviceName: UIDevice.current.name)
      server = saved.origin.absoluteString
      let service = try NativeService(server: server, vault: TokenVault(account: server))
      let user = try await service.me()
      try await attach(user, service: service)
      defaults.set(
        try JSONEncoder().encode(Connection(server: server, person: user)), forKey: "pig.connection"
      )
      await refresh()
      startLiveUpdates()
    } catch OnboardingError.accountCreatedSignInFailed(let username) {
      message = "Account created for \(username). Sign in to finish connecting."
    } catch { message = error.localizedDescription }
  }
  func signIn(username: String, password: String) async {
    guard !busy else { return }
    busy = true
    message = nil
    defer { busy = false }
    do {
      let origin = try ServerAddress.validate(server)
      let service = try NativeService(
        server: origin.absoluteString, vault: TokenVault(account: origin.absoluteString))
      let user = try await service.signIn(
        username: username, password: password, deviceName: UIDevice.current.name)
      server = origin.absoluteString
      try await attach(user, service: service)
      defaults.set(
        try JSONEncoder().encode(Connection(server: server, person: user)), forKey: "pig.connection"
      )
      await refresh()
      startLiveUpdates()
    } catch { message = error.localizedDescription }
  }
  private func attach(_ user: Person, service: NativeService) async throws {
    generation += 1
    let stamp = generation
    let base = try FileManager.default.url(
      for: .applicationSupportDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
    let origin = await service.server
    guard generation == stamp else { throw CancellationError() }
    let directory = base.appendingPathComponent("PigMusic").appendingPathComponent(
      LibraryNamespace.key(server: origin, personId: user.id))
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    var excluded = directory
    var values = URLResourceValues()
    values.isExcludedFromBackup = true
    try excluded.setResourceValues(values)
    let database = try LibraryStore(path: directory.appendingPathComponent("library.sqlite").path)
    let cacheBase = try FileManager.default.url(
      for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
    try await player.configureSources(
      directory: cacheBase.appendingPathComponent("PigMusic").appendingPathComponent(
        LibraryNamespace.key(server: origin, personId: user.id)
      ).appendingPathComponent("audio"))
    guard generation == stamp else { throw CancellationError() }
    artworkCache = try? ArtworkCache(directory: directory.appendingPathComponent("artwork"))
    artworkNamespace = LibraryNamespace.key(server: origin, personId: user.id)
    artworkMemory.removeAllObjects()
    server = origin.absoluteString
    self.service = service
    store = database
    let backgroundIdentifier = "au.com.pig.music.downloads." + artworkNamespace
    let archive =
      try BackgroundTransferHub.archive(for: backgroundIdentifier)
      ?? DownloadArchive(directory: directory.appendingPathComponent("Downloads"))
    downloads = DownloadController(archive: archive, source: service) { [weak self] error in
      if error as? NativeFailure == .authentication {
        self?.revoked(generation: stamp)
      } else if case OfflineFailure.authentication = error {
        self?.revoked(generation: stamp)
      } else {
        self?.message = error.localizedDescription
      }
    }
    downloads?.budgetBytes = Int64(
      defaults.object(forKey: "pig.download-budget:" + artworkNamespace) as? Int
        ?? (5 * 1024 * 1024 * 1024))
    try downloads?.enableBackground(
      identifier: backgroundIdentifier,
      directory: directory.appendingPathComponent("BackgroundTransfers"))
    await downloads?.reload()
    try await watch?.configure(directory: directory, namespace: artworkNamespace)
    var restoredQueue = try? await database.cached("playback", as: PlaybackCheckpoint.self)
    if let old = restoredQueue,
      let position = try? await database.cached("playback-position", as: PlaybackPosition.self)
    {
      var queue = old.queue
      queue.select(index: position.index)
      restoredQueue = PlaybackCheckpoint(queue: queue, elapsed: position.elapsed)
    }
    var savedOccurrenceIds = restoredQueue?.queue.items.map(\.id) ?? []
    player.onListen = { [weak self] event in
      Task {
        try? await database.recordListen(event)
        await self?.flushHistory()
      }
    }
    player.onUpcoming = { [weak self] tracks in
      guard let self, let service = self.service else { return }
      let archive = self.downloads?.archive
      Task {
        var remote: [Track] = []
        for track in tracks where await archive?.localFile(track) == nil { remote.append(track) }
        await service.prepareRemote(remote)
      }
    }
    player.onCheckpoint = { checkpoint in
      let ids = checkpoint.queue.items.map(\.id)
      let changed = ids != savedOccurrenceIds
      savedOccurrenceIds = ids
      Task {
        if changed { try? await database.cache(checkpoint, key: "playback") }
        try? await database.cache(
          PlaybackPosition(index: checkpoint.queue.index, elapsed: checkpoint.elapsed),
          key: "playback-position")
      }
    }
    if let restoredQueue, restoredQueue.queue.current != nil {
      play(
        restoredQueue.queue.items.map(\.track), at: restoredQueue.queue.index,
        restored: restoredQueue)
    }
    searchSession = SearchSession(cached: database, online: service) { [weak self] in
      self?.revoked(generation: stamp)
    }
    sync = SyncCoordinator(source: service, store: database)
    person = user
    preferences =
      (try? await database.cached("preferences", as: AccountPreferences.self))
      ?? AccountPreferences()
    for section in HomeSection.allCases {
      homeContent[section] = try? await database.cached(
        "home:" + section.rawValue, as: HomeContent.self)
    }
    try await loadCache()
    pendingEdits = (try? await database.pendingMutations()) ?? []
  }
  func refresh(afterMutation: Bool = false) async {
    guard !syncing, !mutationActive || afterMutation, let service, let sync else { return }
    let stamp = generation
    syncing = true
    defer { if generation == stamp { syncing = false } }
    do {
      let current = try await service.me()
      guard generation == stamp else { return }
      guard current.id == person?.id else {
        detach()
        message = "The server account changed. Please sign in again."
        return
      }
      watch?.confirmAccount()
      try await sync.refresh()
      guard generation == stamp else { return }
      try await loadCache()
      let revisions = await player.cachedRevisions()
      guard generation == stamp else { return }
      var invalid = false
      for (id, revision) in revisions {
        let track = try await store?.track(id: id)
        if track == nil || track?.sourceRevision != revision {
          invalid = true
          break
        }
      }
      guard generation == stamp else { return }
      if let downloads {
        var allowed: [String: String?] = [:]
        for record in downloads.records {
          if let track = try await store?.track(id: record.id) {
            allowed.updateValue(track.sourceRevision, forKey: record.id)
            if record.state == "ready" && record.track.sourceRevision != track.sourceRevision {
              invalid = true
            }
          } else if record.state == "ready" {
            invalid = true
          }
        }
        if invalid { await player.invalidateSources() }
        await downloads.reconcile(allowed)
        guard generation == stamp else { return }
        downloads.resume(automatic: true)
      } else if invalid {
        await player.invalidateSources()
      }
      guard generation == stamp else { return }
      if !pendingEdits.contains(where: { $0.mutation.action == "preferences" }),
        let settings = try? await service.preferences(), generation == stamp
      {
        preferences = settings
        await cachePreferences()
      }
      let editsApplied = await flushEdits()
      guard generation == stamp else { return }
      if editsApplied {
        try await sync.refresh()
        try await loadCache()
        if let settings = try? await service.preferences(), generation == stamp {
          preferences = settings
          await cachePreferences()
        }
      }
      try await watch?.reconcile()
      await flushHistory()
      await refreshServerRequests()
      guard generation == stamp else { return }
      message =
        invalid ? "Playback stopped because the server changed or removed cached music." : nil
    } catch NativeFailure.authentication {
      guard generation == stamp else { return }
      revoked(generation: stamp)
    } catch {
      guard generation == stamp else { return }
      message = "Showing your cached library. " + error.localizedDescription
    }
  }
  private func loadCache() async throws {
    guard let store else { return }
    let stamp = generation
    let tracks = try await store.tracks(sort: songSort)
    let albums = try await store.albums(category: albumCategory, sort: albumSort)
    let artists = try await store.artists(sort: artistSort)
    let playlists = try await store.playlists()
    let count = try await store.count(.tracks)
    let categoryCounts = try await store.albumCategoryCounts()
    let artistCount = try await store.ownArtistCount()
    guard generation == stamp else { return }
    songs = tracks
    self.albums = albums
    self.artists = artists
    self.playlists = playlists
    songCount = count
    albumCategoryCounts = categoryCounts
    albumCount = categoryCounts[albumCategory] ?? 0
    self.artistCount = artistCount
    artistCovers = [:]
    artworkRefresh += 1
  }
  func refreshHome(force: Bool = false) async {
    guard let service else { return }
    let sections = HomeSection.allCases.filter {
      !homeLoading.contains($0) && (force || (homeContent[$0] == nil && homeErrors[$0] == nil))
    }
    guard !sections.isEmpty else { return }
    let stamp = generation
    homeLoading.formUnion(sections)
    for section in sections { homeErrors[section] = nil }
    await withTaskGroup(of: (HomeSection, Result<HomeContent, NativeFailure>).self) { group in
      for section in sections {
        group.addTask {
          do {
            return (section, .success(try await service.home(section)))
          } catch let failure as NativeFailure {
            return (section, .failure(failure))
          } catch {
            return (section, .failure(.unavailable(error.localizedDescription)))
          }
        }
      }
      for await (section, result) in group {
        guard generation == stamp, !Task.isCancelled else {
          group.cancelAll()
          continue
        }
        homeLoading.remove(section)
        switch result {
        case .success(let content):
          homeContent[section] = content
          try? await store?.cache(content, key: "home:" + section.rawValue)
        case .failure(.authentication):
          group.cancelAll()
          revoked(generation: stamp)
        case .failure(let error): homeErrors[section] = error.localizedDescription
        }
      }
    }
    if generation == stamp { homeLoading.subtract(sections) }
  }

  func readCatalogue<T: Sendable>(
    _ fetch: @Sendable (NativeService) async throws -> T
  ) async throws -> T {
    guard let service else {
      throw NativeFailure.unavailable("Connect to your server to browse the catalogue.")
    }
    let stamp = generation
    do {
      let value = try await fetch(service)
      try Task.checkCancellation()
      guard generation == stamp else { throw CancellationError() }
      return value
    } catch NativeFailure.authentication {
      revoked(generation: stamp)
      throw NativeFailure.authentication
    }
  }

  func performPersonal<T: Sendable>(
    _ operation: @Sendable (NativeService) async throws -> T
  ) async throws -> T {
    guard canMutate, let service else {
      throw NativeFailure.unavailable("Connect to your server and wait for sync to finish.")
    }
    let stamp = generation
    mutationActive = true
    defer { if generation == stamp { mutationActive = false } }
    do {
      let result = try await operation(service)
      try Task.checkCancellation()
      guard generation == stamp else { throw CancellationError() }
      await refresh(afterMutation: true)
      guard generation == stamp else { throw CancellationError() }
      return result
    } catch NativeFailure.authentication {
      revoked(generation: stamp)
      throw NativeFailure.authentication
    }
  }

  @discardableResult func saveEdit(_ mutation: OfflineMutation) async throws -> Bool {
    guard let store, person != nil else { throw NativeFailure.authentication }
    let stamp = generation
    try await store.enqueueMutation(mutation)
    guard generation == stamp else { throw CancellationError() }
    pendingEdits = try await store.pendingMutations()
    let applied = await flushEdits()
    guard generation == stamp else { throw CancellationError() }
    if applied { await refresh() }
    return !pendingEdits.contains { $0.id == mutation.id }
  }
  @discardableResult func flushEdits() async -> Bool {
    guard !flushingEdits, let store, let service, person != nil else { return false }
    flushingEdits = true
    let stamp = generation
    defer { flushingEdits = false }
    var applied = false
    do {
      while let first = try await store.pendingMutations().first, first.state == "queued" {
        guard generation == stamp else { return applied }
        do {
          let receipt = try await service.applyMutation(first.mutation)
          guard receipt.applied, receipt.operationId == first.id, generation == stamp else {
            return applied
          }
          try await store.acknowledgeMutation(first.id)
          applied = true
        } catch NativeFailure.authentication {
          revoked(generation: stamp)
          return applied
        } catch NativeFailure.changed {
          var changed = first
          changed.state = "conflict"
          changed.message =
            "This playlist changed on the server. Discard this edit or review the current playlist before reapplying it."
          try await store.updateMutation(changed)
          break
        } catch is MutationRejection {
          var rejected = first
          rejected.state = "rejected"
          rejected.message = "The server could not apply this edit. Review its song or playlist."
          try await store.updateMutation(rejected)
          break
        } catch {
          break
        }
      }
      if generation == stamp { pendingEdits = try await store.pendingMutations() }
    } catch { if generation == stamp { message = error.localizedDescription } }
    return applied
  }
  func discardEdit(_ id: String) async {
    guard !flushingEdits, let store else { return }
    try? await store.acknowledgeMutation(id)
    pendingEdits = (try? await store.pendingMutations()) ?? []
    _ = await flushEdits()
    await refresh()
  }
  func cachedCatalogue<T: Codable & Sendable>(
    key: String, load: @Sendable (NativeService) async throws -> T
  ) async throws -> T {
    let stamp = generation
    let database = store
    do {
      let result = try await readCatalogue(load)
      guard generation == stamp else { throw CancellationError() }
      remember(result, key: key)
      try? await database?.cache(result, key: "catalogue:" + key)
      return result
    } catch NativeFailure.authentication {
      throw NativeFailure.authentication
    } catch is CancellationError { throw CancellationError() } catch {
      guard generation == stamp else { throw CancellationError() }
      if let saved = try? await database?.cached("catalogue:" + key, as: T.self) { return saved }
      throw error
    }
  }
  /// The last catalogue answer for a key, so a revisited page draws at once.
  /// Pages still refresh it through `cachedCatalogue`.
  func peekCatalogue<T: Sendable>(key: String, as type: T.Type = T.self) -> T? {
    catalogueMemory[key] as? T
  }
  /// The memory answer, else the one saved on this device from an earlier session.
  func storedCatalogue<T: Codable & Sendable>(key: String, as type: T.Type = T.self) async -> T? {
    if let value = peekCatalogue(key: key, as: T.self) { return value }
    let stamp = generation
    guard let saved = try? await store?.cached("catalogue:" + key, as: T.self),
      generation == stamp
    else { return nil }
    remember(saved, key: key)
    return saved
  }
  private func remember(_ value: any Sendable, key: String) {
    if catalogueMemory.count > 400 { catalogueMemory.removeAll() }
    catalogueMemory[key] = value
  }
  /// Artwork addressed by stored hash, or a server alias for catalogue items.
  enum ArtworkSource: Hashable, Sendable {
    case stored(String)
    case release(String)
    case releaseGroup(String)
    case artist(String)
  }
  func artwork(_ source: ArtworkSource?, width: Int = 256) async -> UIImage? {
    switch source {
    case .stored(let sha): return await artwork(sha: sha, width: width)
    case .release(let id):
      return await catalogueImage("release", id, width) {
        try await $0.catalogueArtwork(kind: .release, id: id, request: $1)
      }
    case .releaseGroup(let id):
      return await catalogueImage("release-group", id, width) {
        try await $0.catalogueArtwork(kind: .releaseGroup, id: id, request: $1)
      }
    case .artist(let id):
      return await catalogueImage("artist", id, width) {
        try await $0.artistArtwork(id: id, request: $1)
      }
    case nil: return nil
    }
  }
  func artistArtwork(id: String) async -> UIImage? { await artwork(.artist(id), width: 512) }
  /// Fanart background and logo for the full artist page; nil when unavailable.
  func artistBackground(id: String) async -> UIImage? {
    await catalogueImage("background", id, 1024) {
      try await $0.artistBackground(id: id, request: $1)
    }
  }
  func artistLogo(id: String) async -> UIImage? {
    await catalogueImage("logo", id, 1024) { service, _ in try await service.artistLogo(id: id) }
  }
  /// The image already decoded in memory, for drawing a revisited page at once.
  func memoryCatalogueImage(_ kind: String, _ id: String, width: Int) -> UIImage? {
    let sha = SHA256.hash(data: Data(("catalogue-\(kind):" + id.lowercased()).utf8)).map {
      String(format: "%02x", $0)
    }.joined()
    guard let request = try? ArtworkRequest(sha: sha, width: width) else { return nil }
    return artworkMemory.object(forKey: request.filename as NSString)
  }
  private func catalogueImage(
    _ kind: String, _ id: String, _ width: Int,
    fetch: @escaping @Sendable (NativeService, ArtworkRequest) async throws -> Data
  ) async -> UIImage? {
    guard let service, let cache = artworkCache, UUID(uuidString: id) != nil else { return nil }
    let stamp = generation
    // Catalogue artwork has no content hash on the client: key it by its alias.
    let sha = SHA256.hash(data: Data(("catalogue-\(kind):" + id.lowercased()).utf8)).map {
      String(format: "%02x", $0)
    }.joined()
    guard let request = try? ArtworkRequest(sha: sha, width: width) else { return nil }
    let key = request.filename as NSString
    if let image = artworkMemory.object(forKey: key) { return image }
    do {
      let data = try await cache.data(for: request) { try await fetch(service, $0) }
      let decoded = try await Task.detached(priority: .utility) {
        try ArtworkCache.thumbnail(data, width: width)
      }.value
      guard generation == stamp else { return nil }
      let image = UIImage(cgImage: decoded)
      artworkMemory.setObject(image, forKey: key, cost: decoded.bytesPerRow * decoded.height)
      return image
    } catch NativeFailure.authentication {
      revoked(generation: stamp)
      return nil
    } catch { return nil }
  }
  /// A saved artist shows their first album cover with artwork.
  /// The library artist behind an album or catalogue page, by ID or else by exact name.
  func savedArtist(id: String? = nil, name: String) async -> Artist? {
    guard let store else { return nil }
    if let id, let artist = try? await store.artist(id: id) { return artist }
    return try? await store.artist(named: name)
  }
  func artistCover(_ artist: Artist) async -> String? {
    if let cached = artistCovers[artist.id] { return cached }
    guard let store else { return nil }
    var albums = (try? await store.albums(artistId: artist.id, limit: 12)) ?? []
    if let preferred = artist.coverAlbumId,
      let index = albums.firstIndex(where: { $0.id == preferred })
    {
      albums.insert(albums.remove(at: index), at: 0)
    }
    let sha = albums.lazy.compactMap(\.coverSha).first
    artistCovers[artist.id] = sha
    return sha
  }
  func sortLibrary(_ collection: LibraryCollection, by sort: LibrarySort) async {
    guard !loadingMore, !syncing else { return }
    switch collection {
    case .tracks: songSort = sort
    case .albums: albumSort = sort
    case .artists: artistSort = sort
    case .playlists: return
    }
    do { try await loadCache() } catch { message = error.localizedDescription }
  }
  /// Where a song's file is on this side of the server: iPhone and Apple Watch.
  func deviceCopies(_ trackId: String) -> (phone: DeviceCopyMark?, watch: DeviceCopyMark?) {
    let phone = downloads?.records.first { $0.id == trackId }.map {
      $0.state == "ready" ? DeviceCopyMark.ready : $0.state == "failed" ? .failed : .pending
    }
    var watchMark: DeviceCopyMark?
    if let record = watch?.downloads?.records.first(where: { $0.id == trackId }) {
      let onWatch =
        record.checksum != nil && watch?.receipt?.ready[trackId] == record.checksum
      watchMark = onWatch ? .ready : record.state == "failed" ? .failed : .pending
    } else if watch?.receipt?.ready[trackId] != nil {
      watchMark = .ready
    }
    return (phone, watchMark)
  }
  func phoneProgress(_ trackId: String) -> Double {
    guard let record = downloads?.records.first(where: { $0.id == trackId }), record.total > 0
    else { return 0 }
    return min(1, Double(record.bytes) / Double(record.total))
  }
  /// Active means requested and not yet finished (queued or downloading), so
  /// sending a 10-song album shows 10 and counts down to 0.
  var phoneActiveDownloads: Int {
    downloads?.records.count { $0.state != "ready" && $0.state != "failed" } ?? 0
  }
  var watchActiveDownloads: Int {
    let receipt = watch?.receipt
    return watch?.downloads?.records.count {
      $0.state != "failed" && ($0.checksum == nil || receipt?.ready[$0.id] != $0.checksum)
    } ?? 0
  }
  /// The Downloads tab badge: the three sections' active counts combined.
  var pendingDownloadCount: Int {
    serverActiveRequests + phoneActiveDownloads + watchActiveDownloads
  }
  func refreshServerRequests() async {
    guard let page = try? await readCatalogue({ try await $0.requests(limit: 1) }) else { return }
    serverActiveRequests = page.active
  }
  func showAlbums(category: String) async {
    guard category != albumCategory else { return }
    albumCategory = category
    albums = []
    albumCount = albumCategoryCounts[category] ?? 0
    guard !syncing else { return }  // The sync's own reload uses the new category.
    do { try await loadCache() } catch { message = error.localizedDescription }
  }
  func more(_ collection: LibraryCollection) async {
    guard let store, !loadingMore, !syncing else { return }
    let stamp = generation
    loadingMore = true
    defer { if generation == stamp { loadingMore = false } }
    do {
      switch collection {
      case .tracks:
        let next = try await store.tracks(offset: songs.count, sort: songSort)
        guard generation == stamp else { return }
        songs += next
      case .albums:
        let next = try await store.albums(
          category: albumCategory, offset: albums.count, sort: albumSort)
        guard generation == stamp else { return }
        albums += next
      case .artists:
        let next = try await store.artists(offset: artists.count, sort: artistSort)
        guard generation == stamp else { return }
        artists += next
      case .playlists: break
      }
    } catch { message = error.localizedDescription }
  }
  func albumTracks(_ album: Album) async -> [Track] {
    (try? await store?.tracks(albumId: album.id)) ?? []
  }
  func artwork(sha: String?, width: Int = 256) async -> UIImage? {
    guard let sha, let request = try? ArtworkRequest(sha: sha, width: width),
      let cache = artworkCache
    else { return nil }
    let service = self.service
    var demoData: Data?
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("--demo") {
        demoData = demoArtwork(request)
      }
    #endif
    guard service != nil || demoData != nil else { return nil }
    let stamp = generation
    let key = request.filename as NSString
    if let image = artworkMemory.object(forKey: key) { return image }
    do {
      let synthetic = demoData
      let data = try await cache.data(for: request) {
        if let synthetic { return synthetic }
        guard let service else { throw ArtworkFailure.unavailable }
        return try await service.artwork($0)
      }
      try Task.checkCancellation()
      let decoded = try await Task.detached(priority: .utility) {
        try ArtworkCache.thumbnail(data, width: width)
      }.value
      try Task.checkCancellation()
      guard generation == stamp else { return nil }
      let image = UIImage(cgImage: decoded)
      artworkMemory.setObject(image, forKey: key, cost: decoded.bytesPerRow * decoded.height)
      return image
    } catch NativeFailure.authentication {
      revoked(generation: stamp)
      return nil
    } catch { return nil }
  }
  func flushHistory() async {
    guard !flushingHistory, let database = store, let service else { return }
    let stamp = generation
    flushingHistory = true
    defer { flushingHistory = false }
    do {
      let pending = try await database.pendingListens()
      var valid: [ListeningEvent] = []
      var discarded: [String] = []
      let now = Int(Date().timeIntervalSince1970)
      for event in pending {
        let exists = try await database.track(id: event.trackId) != nil
        if event.playedAt < now - 30 * 86400 || event.playedAt > now + 300 || !exists {
          discarded.append(event.id)
        } else {
          valid.append(event)
        }
      }
      try await database.acknowledgeListens(discarded)
      guard generation == stamp else { return }
      try await service.recordListens(valid)
      guard generation == stamp else { return }
      try await database.acknowledgeListens(valid.map(\.id))
    } catch NativeFailure.authentication { revoked(generation: stamp) } catch {
      // Durable events remain queued until the next confirmed connection.
    }
  }
  func shuffleLibrary() async {
    guard let store else { return }
    let stamp = generation
    do {
      let tracks = try await store.tracks(limit: max(songCount, 1))
      guard generation == stamp else { return }
      play(tracks.shuffled())
    } catch { message = error.localizedDescription }
  }
  func play(_ tracks: [Track], at index: Int = 0, restored: PlaybackCheckpoint? = nil) {
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("--demo"),
        let url = Bundle.main.url(forResource: "demo-tone", withExtension: "m4a")
      {
        player.play(
          tracks, startingAt: index,
          artwork: { [weak self] track in
            await self?.artwork(track.artworkSource, width: 512)
          }, resolve: { _ in url }
        )
        return
      }
    #endif
    guard !busy || restored != nil, let service else { return }
    let archive = downloads?.archive
    let stamp = generation
    player.play(
      tracks, startingAt: index, autoplay: restored == nil, restored: restored,
      artwork: { [weak self] track in
        await self?.artwork(track.artworkSource, width: 512)
      },
      resolve: { [weak self] track in
        do {
          if let local = await archive?.localFile(track) { return local }
          return try await service.resolve(track)
        } catch NativeFailure.authentication {
          await self?.revoked(generation: stamp)
          throw NativeFailure.authentication
        }
      }
    )
  }
  func signOut() async {
    guard !busy, !mutationActive else { return }
    guard let service else {
      detach()
      return
    }
    busy = true
    defer { busy = false }
    do {
      try await service.signOut()
      detach()
    } catch { message = error.localizedDescription }
  }
  private func detach() {
    watch?.disconnect()
    generation += 1
    liveTask?.cancel()
    liveTask = nil
    if let downloads { Task { await downloads.clear() } }
    downloads = nil
    searchSession?.clear()
    searchSession = nil
    actionTrack = nil
    mutationActive = false
    pendingEdits = []
    player.clearAccount()
    preferences = AccountPreferences()
    person = nil
    service = nil
    store = nil
    sync = nil
    if let cache = artworkCache { Task { await cache.cancelPending() } }
    artworkCache = nil
    artworkNamespace = ""
    artworkMemory.removeAllObjects()
    artistCovers = [:]
    catalogueMemory = [:]
    homeContent = [:]
    homeErrors = [:]
    homeLoading = []
    songs = []
    albums = []
    artists = []
    playlists = []
    songCount = 0
    albumCount = 0
    artistCount = 0
    albumCategory = "album"
    albumCategoryCounts = [:]
    syncing = false
    loadingMore = false
    defaults.removeObject(forKey: "pig.connection")
  }
  private func revoked(generation stamp: Int) {
    guard generation == stamp else { return }
    detach()
    message = "This device session was revoked or expired. Please sign in again."
  }
  #if DEBUG
    private func loadDemo() async {
      do {
        let fixture =
          #"{"revision":"demo","tracks":[{"id":"one","title":"First Light","artist":"The Orchard","album":"Sunrise","album_id":"sunrise","track_number":1,"duration":3},{"id":"two","title":"Open Road","artist":"The Orchard","album":"Sunrise","album_id":"sunrise","track_number":2,"duration":3},{"id":"three","title":"After the Rain","artist":"Riverlight","album":"Quiet Hours","album_id":"quiet","track_number":1,"duration":3}],"albums":[{"id":"sunrise","title":"Sunrise","artist":"The Orchard","track_count":2},{"id":"quiet","title":"Quiet Hours","artist":"Riverlight","track_count":1}],"artists":[{"id":"orchard","name":"The Orchard","track_count":2},{"id":"river","name":"Riverlight","track_count":1}],"playlists":[]}"#
        let database = try LibraryStore(path: ":memory:")
        var snapshot = try LibraryCodec.decoder().decode(
          LibrarySnapshot.self, from: Data(fixture.utf8))
        for index in snapshot.tracks.indices {
          snapshot.tracks[index].coverSha = String(
            repeating: snapshot.tracks[index].albumId == "sunrise" ? "a" : "b", count: 64)
        }
        for index in snapshot.albums.indices {
          snapshot.albums[index].coverSha = String(
            repeating: snapshot.albums[index].id == "sunrise" ? "a" : "b", count: 64)
        }
        homeContent[.recent] = HomeContent(albums: snapshot.albums)
        try await database.replace(snapshot)
        let demoDirectory = try FileManager.default.url(
          for: .cachesDirectory, in: .userDomainMask, appropriateFor: nil, create: true
        )
        .appendingPathComponent("PigMusicDemoArtwork-v1")
        try await player.configureSources(directory: demoDirectory.appendingPathComponent("audio"))
        artworkCache = try ArtworkCache(directory: demoDirectory)
        artworkNamespace = "synthetic-demo"
        store = database
        searchSession = SearchSession(cached: database)
        person = try LibraryCodec.decoder().decode(
          Person.self,
          from: Data(
            #"{"id":"demo","username":"demo","display_name":"Demo listener","role":"member"}"#.utf8)
        )
        server = "https://demo.invalid"
        try await loadCache()
      } catch { message = error.localizedDescription }
    }
    private func demoArtwork(_ request: ArtworkRequest) -> Data? {
      let format = UIGraphicsImageRendererFormat()
      format.scale = 1
      let size = CGSize(width: request.width, height: request.width)
      return UIGraphicsImageRenderer(size: size, format: format).pngData { context in
        let warm = request.sha.hasPrefix("a")
        (warm
          ? UIColor(red: 0.9, green: 0.35, blue: 0.3, alpha: 1)
          : UIColor(red: 0.18, green: 0.38, blue: 0.55, alpha: 1)).setFill()
        context.fill(CGRect(origin: .zero, size: size))
        UIColor.white.withAlphaComponent(0.3).setFill()
        context.cgContext.fillEllipse(
          in: CGRect(
            x: size.width * 0.18, y: size.height * 0.18, width: size.width * 0.64,
            height: size.height * 0.64))
        let title = warm ? "SUNRISE" : "QUIET HOURS"
        let font = UIFont.boldSystemFont(ofSize: size.width * 0.07)
        let attributes: [NSAttributedString.Key: Any] = [
          .font: font, .foregroundColor: UIColor.white,
        ]
        let textSize = title.size(withAttributes: attributes)
        title.draw(
          at: CGPoint(x: (size.width - textSize.width) / 2, y: size.height * 0.8),
          withAttributes: attributes)
      }
    }
  #endif
}

enum DeviceCopyMark { case pending, ready, failed }
