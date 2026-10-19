import Foundation
import Observation
import PigDomain
import PigStore

public protocol CachedSearchSource: Sendable {
  func searchPage(query: String, offset: Int, limit: Int) async throws -> LibrarySearchPage
}
extension LibraryStore: CachedSearchSource {}
public protocol OnlineSearchSource: Sendable {
  func searchServer(query: String, offset: Int, revision: String?) async throws -> ServerSearchPage
  func catalogueArtists(query: String, offset: Int) async throws -> CatalogueArtistPage
}
extension NativeService: OnlineSearchSource {}

private enum SearchLane: Sendable { case cached, household, catalogue }
private enum SearchDelivery: Sendable {
  case cached(LibrarySearchPage)
  case household(ServerSearchPage)
  case catalogue(CatalogueArtistPage)
  case failure(SearchLane, NativeFailure)
}

@available(macOS 14, *)
@MainActor @Observable public final class SearchSession {
  public private(set) var query = ""
  public private(set) var tracks: [Track] = []
  public private(set) var albums: [Album] = []
  public private(set) var artists: [Artist] = []
  public private(set) var household: [Track] = []
  public private(set) var catalogue: [CatalogueArtist] = []
  public private(set) var localNext: Int?
  public private(set) var householdNext: Int?
  public private(set) var catalogueNext: Int?
  public private(set) var localLoading = false
  public private(set) var householdLoading = false
  public private(set) var catalogueLoading = false
  public private(set) var localError: String?
  public private(set) var householdError: String?
  public private(set) var catalogueError: String?
  public let onlineEnabled: Bool
  @ObservationIgnored private let cached: any CachedSearchSource
  @ObservationIgnored private let online: (any OnlineSearchSource)?
  @ObservationIgnored private let onAuthentication: @MainActor () -> Void
  @ObservationIgnored private var generation = 0
  @ObservationIgnored private var localRevision = ""
  @ObservationIgnored private var serverRevision = ""
  /// First pages of server and catalogue answers by query, reused while
  /// fresh, so backspacing or retyping sends no request.
  @ObservationIgnored private var answers: [String: OnlineAnswer] = [:]
  private struct OnlineAnswer {
    var time: Date
    var household: ServerSearchPage?
    var catalogue: CatalogueArtistPage?
  }
  public static let answerLifetime: TimeInterval = 300

  public init(
    cached: any CachedSearchSource, online: (any OnlineSearchSource)? = nil,
    onAuthentication: @escaping @MainActor () -> Void = {}
  ) {
    self.cached = cached
    self.online = online
    self.onlineEnabled = online != nil
    self.onAuthentication = onAuthentication
  }
  public func clear() {
    generation += 1
    query = ""
    tracks = []
    albums = []
    artists = []
    household = []
    catalogue = []
    localNext = nil
    householdNext = nil
    catalogueNext = nil
    localLoading = false
    householdLoading = false
    catalogueLoading = false
    localError = nil
    householdError = nil
    catalogueError = nil
    localRevision = ""
    serverRevision = ""
  }
  /// `force` (Refresh) asks the server again instead of reusing an answer.
  public func search(_ text: String, force: Bool = false, now: Date = Date()) async {
    clear()
    query = SearchText.clean(text)
    guard !query.isEmpty else { return }
    let query = self.query
    let stamp = generation
    let key = SearchText.key(query)
    if force { answers[key] = nil }
    if let answer = answers[key], now.timeIntervalSince(answer.time) > Self.answerLifetime {
      answers[key] = nil
    }
    let reuse = answers[key]
    if let page = reuse?.household { accept(page, append: false) }
    if let page = reuse?.catalogue {
      catalogue = page.artists
      catalogueNext = page.nextOffset
    }
    let wantsCatalogue = query.count >= SearchText.catalogueMinimum
    localLoading = true
    householdLoading = onlineEnabled && reuse?.household == nil
    catalogueLoading = onlineEnabled && wantsCatalogue && reuse?.catalogue == nil
    let askHousehold = householdLoading
    let askCatalogue = catalogueLoading
    let cached = self.cached
    let online = self.online
    await withTaskGroup(of: SearchDelivery.self) { group in
      group.addTask {
        do {
          return .cached(try await cached.searchPage(query: query, offset: 0, limit: 100))
        } catch {
          return .failure(
            .cached, error as? NativeFailure ?? .unavailable(error.localizedDescription))
        }
      }
      if let online, askHousehold {
        group.addTask {
          do {
            return .household(try await online.searchServer(query: query, offset: 0, revision: nil))
          } catch {
            return .failure(
              .household, error as? NativeFailure ?? .unavailable(error.localizedDescription))
          }
        }
      }
      if let online, askCatalogue {
        group.addTask {
          do {
            return .catalogue(try await online.catalogueArtists(query: query, offset: 0))
          } catch {
            return .failure(
              .catalogue, error as? NativeFailure ?? .unavailable(error.localizedDescription))
          }
        }
      }
      for await result in group {
        guard generation == stamp, !Task.isCancelled else {
          group.cancelAll()
          continue
        }
        switch result {
        case .cached(let page):
          accept(page, append: false)
          localLoading = false
        case .household(let page):
          accept(page, append: false)
          householdLoading = false
          remember(key, now: now) { $0.household = page }
        case .catalogue(let page):
          catalogue = page.artists
          catalogueNext = page.nextOffset
          catalogueLoading = false
          remember(key, now: now) { $0.catalogue = page }
        case .failure(let lane, let failure):
          if failure == .authentication {
            group.cancelAll()
            clear()
            onAuthentication()
            continue
          }
          switch lane {
          case .cached:
            localError = failure.localizedDescription
            localLoading = false
          case .household:
            householdError = failure.localizedDescription
            householdLoading = false
          case .catalogue:
            catalogueError = failure.localizedDescription
            catalogueLoading = false
          }
        }
      }
    }
    if generation == stamp {
      localLoading = false
      householdLoading = false
      catalogueLoading = false
    }
  }
  private func remember(_ key: String, now: Date, _ update: (inout OnlineAnswer) -> Void) {
    if answers[key] == nil, answers.count >= 60 {
      // Drop the oldest answer to stay small.
      if let oldest = answers.min(by: { $0.value.time < $1.value.time })?.key {
        answers[oldest] = nil
      }
    }
    var answer = answers[key] ?? OnlineAnswer(time: now)
    update(&answer)
    answers[key] = answer
  }
  private func accept(_ page: LibrarySearchPage, append: Bool) {
    tracks = append ? tracks + page.tracks : page.tracks
    albums = append ? albums + page.albums : page.albums
    artists = append ? artists + page.artists : page.artists
    localNext = page.nextOffset
    localRevision = page.revision
  }
  private func accept(_ page: ServerSearchPage, append: Bool) {
    household = append ? household + page.householdTracks : page.householdTracks
    householdNext = page.offset + 100 < page.totalHouseholdTracks ? page.offset + 100 : nil
    serverRevision = page.revision
  }
  public func moreLocal() async {
    guard let offset = localNext, !localLoading else { return }
    let stamp = generation
    let query = self.query
    localLoading = true
    localError = nil
    defer { if generation == stamp { localLoading = false } }
    do {
      let page = try await cached.searchPage(query: query, offset: offset, limit: 100)
      guard generation == stamp, !Task.isCancelled else { return }
      guard page.revision == localRevision else { throw NativeFailure.changed }
      accept(page, append: true)
    } catch {
      if generation == stamp, !Task.isCancelled { localError = error.localizedDescription }
    }
  }
  public func moreHousehold() async {
    guard let online, let offset = householdNext, !householdLoading else { return }
    let stamp = generation
    let query = self.query
    let revision = serverRevision
    householdLoading = true
    householdError = nil
    defer { if generation == stamp { householdLoading = false } }
    do {
      let page = try await online.searchServer(query: query, offset: offset, revision: revision)
      guard generation == stamp, !Task.isCancelled else { return }
      guard page.revision == revision else { throw NativeFailure.changed }
      accept(page, append: true)
    } catch { record(error, lane: .household, stamp: stamp) }
  }
  public func moreCatalogue() async {
    guard let online, let offset = catalogueNext, !catalogueLoading else { return }
    let stamp = generation
    let query = self.query
    catalogueLoading = true
    catalogueError = nil
    defer { if generation == stamp { catalogueLoading = false } }
    do {
      let page = try await online.catalogueArtists(query: query, offset: offset)
      guard generation == stamp, !Task.isCancelled else { return }
      let known = Set(catalogue.map(\.id))
      catalogue += page.artists.filter { !known.contains($0.id) }
      catalogueNext = page.nextOffset
    } catch { record(error, lane: .catalogue, stamp: stamp) }
  }
  private func record(_ error: any Error, lane: SearchLane, stamp: Int) {
    guard generation == stamp, !Task.isCancelled else { return }
    if error as? NativeFailure == .authentication {
      clear()
      onAuthentication()
      return
    }
    switch lane {
    case .cached: localError = error.localizedDescription
    case .household: householdError = error.localizedDescription
    case .catalogue: catalogueError = error.localizedDescription
    }
  }
}
