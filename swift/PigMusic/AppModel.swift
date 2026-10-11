import Foundation
import Observation
import PigAPI
import PigDomain
import PigStore
import PigSync
import UIKit

@MainActor @Observable final class AppModel {
  struct Connection: Codable {
    var server: String
    var person: Person
  }
  var person: Person?
  var server = ""
  var busy = false
  var syncing = false
  var message: String?
  var songs: [Track] = []
  var albums: [Album] = []
  var artists: [Artist] = []
  var playlists: [Playlist] = []
  var homeContent: [HomeSection: HomeContent] = [:]
  var homeErrors: [HomeSection: String] = [:]
  var homeLoading: Set<HomeSection> = []
  var songCount = 0
  var albumCount = 0
  var artistCount = 0
  var loadingMore = false
  let player = PlayerController()
  var artworkNamespace = ""
  var artworkRefresh = 0
  @ObservationIgnored private var artworkCache: ArtworkCache?
  @ObservationIgnored private let artworkMemory = NSCache<NSString, UIImage>()
  @ObservationIgnored private(set) var service: NativeService?
  @ObservationIgnored private(set) var store: LibraryStore?
  @ObservationIgnored private var sync: SyncCoordinator?
  @ObservationIgnored private var generation = 0
  @ObservationIgnored private var restoring = false
  @ObservationIgnored private let defaults: UserDefaults
  init(defaults: UserDefaults = .standard) {
    self.defaults = defaults
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
    sync = SyncCoordinator(source: service, store: database)
    person = user
    try await loadCache()
  }
  func refresh() async {
    guard !syncing, let service, let sync else { return }
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
      if invalid { await player.invalidateSources() }
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
    let tracks = try await store.tracks()
    let albums = try await store.albums()
    let artists = try await store.artists()
    let playlists = try await store.playlists()
    let count = try await store.count(.tracks)
    let albumCount = try await store.count(.albums)
    let artistCount = try await store.count(.artists)
    guard generation == stamp else { return }
    songs = tracks
    self.albums = albums
    self.artists = artists
    self.playlists = playlists
    songCount = count
    self.albumCount = albumCount
    self.artistCount = artistCount
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
        case .success(let content): homeContent[section] = content
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

  func search(_ query: String) async -> [Track] {
    guard let store else { return [] }
    do { return try await store.tracks(query: query) } catch {
      message = error.localizedDescription
      return []
    }
  }
  func more(_ collection: LibraryCollection) async {
    guard let store, !loadingMore, !syncing else { return }
    let stamp = generation
    loadingMore = true
    defer { if generation == stamp { loadingMore = false } }
    do {
      switch collection {
      case .tracks:
        let next = try await store.tracks(offset: songs.count)
        guard generation == stamp else { return }
        songs += next
      case .albums:
        let next = try await store.albums(offset: albums.count)
        guard generation == stamp else { return }
        albums += next
      case .artists:
        let next = try await store.artists(offset: artists.count)
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
  func play(_ tracks: [Track], at index: Int = 0) {
    #if DEBUG
      if ProcessInfo.processInfo.arguments.contains("--demo"),
        let url = Bundle.main.url(forResource: "demo-tone", withExtension: "m4a")
      {
        player.play(
          tracks, startingAt: index,
          artwork: { [weak self] track in
            await self?.artwork(sha: track.coverSha, width: 512)
          }, resolve: { _ in url }
        )
        return
      }
    #endif
    guard let service else { return }
    let stamp = generation
    player.play(
      tracks, startingAt: index,
      artwork: { [weak self] track in
        await self?.artwork(sha: track.coverSha, width: 512)
      },
      resolve: { [weak self] track in
        do { return try await service.resolve(track) } catch NativeFailure.authentication {
          await self?.revoked(generation: stamp)
          throw NativeFailure.authentication
        }
      }
    )
  }
  func signOut() async {
    guard !busy else { return }
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
    generation += 1
    player.clearAccount()
    person = nil
    service = nil
    store = nil
    sync = nil
    if let cache = artworkCache { Task { await cache.cancelPending() } }
    artworkCache = nil
    artworkNamespace = ""
    artworkMemory.removeAllObjects()
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
