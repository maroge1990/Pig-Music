import PigBrand
import PigDomain
import SwiftUI
import UIKit

/// Full artist page: popular songs and albums, the artist's albums, then a Full
/// discography link and settings. Answers seen before draw at once and refresh quietly.
struct CatalogueArtistView: View {
  let model: AppModel
  let artistId: String
  let name: String
  @State private var profile: CatalogueProfile?
  @State private var popularity: CataloguePopularity?
  @State private var popularSongs: [Track]
  @State private var albums: CatalogueGroups?
  @State private var error: String?
  @State private var saved: Artist?
  @State private var showingLibrary = false
  init(model: AppModel, artistId: String, name: String) {
    self.model = model
    self.artistId = artistId
    self.name = name
    let popular: CataloguePopularity? = model.peekCatalogue(key: "popular:" + artistId)
    _profile = State(initialValue: model.peekCatalogue(key: "profile:" + artistId))
    _popularity = State(initialValue: popular)
    _popularSongs = State(
      initialValue: Self.songs(popular, model.peekCatalogue(key: "popular-matches:" + artistId)))
    _albums = State(initialValue: model.peekCatalogue(key: Self.albumsKey(artistId)))
  }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        DetailHeader(
          model: model, source: .artist(artistId), eyebrow: "ARTIST", title: name,
          subtitle: profileLine, circle: true)
        if saved != nil {
          Button {
            showingLibrary = true
          } label: {
            Label("In your library", systemImage: "checkmark.circle.fill")
              .font(.subheadline.weight(.semibold))
          }
          .buttonStyle(ChipStyle(selected: false))
          .accessibilityHint("Opens \(name) in your library")
        }
        if let description = profile?.description, !description.isEmpty {
          Text(description).font(PigType.subhead).foregroundStyle(.secondary)
        }
        if !popularSongs.isEmpty {
          VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 10) {
              Text("Popular songs").font(.title3.weight(.bold))
              Spacer()
              PlayCapsule { model.play(popularSongs) }
            }.padding(.bottom, 6)
            ForEach(Array(popularSongs.prefix(10).enumerated()), id: \.element.id) {
              index, track in
              SongRow(model: model, track: track) { model.play(popularSongs, at: index) }
              Divider()
            }
          }
        }
        if let popular = popularity, !popular.albums.isEmpty {
          Shelf(title: "Popular albums") {
            ForEach(popular.albums) { release in
              NavigationLink {
                CatalogueAlbumView(model: model, groupId: release.id, title: release.title)
              } label: {
                CollectionCard(
                  model: model, source: .releaseGroup(release.id), title: release.title,
                  caption: String(release.date.prefix(4))
                ).frame(width: 150)
              }.buttonStyle(.plain)
            }
          }.padding(.horizontal, -16)
        }
        if let albums, !albums.releases.isEmpty {
          Text("Albums").font(.title3.weight(.bold))
          ReleaseGrid(model: model, releases: albums.releases.sorted { $0.date > $1.date })
        } else if albums == nil {
          if let error {
            Text(error).font(PigType.footnote).foregroundStyle(.secondary)
            Button("Try again") { Task { await loadAlbums() } }
              .buttonStyle(ChipStyle(selected: false))
          } else {
            ProgressView().frame(maxWidth: .infinity)
          }
        }
        NavigationLink {
          CatalogueDiscographyView(model: model, artistId: artistId, name: name)
        } label: {
          DiscographyLinkLabel()
        }.buttonStyle(.plain)
        DetailSettings {
          NavigationLink {
            ArtistAcquisitionView(model: model, artistId: artistId)
          } label: {
            HStack {
              Label("Requests and monitoring", systemImage: "bell")
              Spacer()
              Image(systemName: "chevron.right").foregroundStyle(.tertiary)
            }
          }
        }
      }.padding(.horizontal).padding(.bottom, 24)
    }
    .pigCanvas().navigationTitle(name).navigationBarTitleDisplayMode(.inline)
    .navigationDestination(isPresented: $showingLibrary) {
      if let saved { SavedArtistView(model: model, artist: saved) }
    }
    .task {
      // Every part loads at once; none waits for another.
      async let profile: Void = loadProfile()
      async let popular: Void = loadPopular()
      async let albums: Void = loadAlbums()
      async let saved: Void = findSaved()
      _ = await (profile, popular, albums, saved)
    }
  }
  static func albumsKey(_ artistId: String) -> String { "groups:\(artistId):album:0" }
  private static func songs(_ popular: CataloguePopularity?, _ matches: [Track?]?) -> [Track] {
    let tracks = popular?.songs.map(\.track) ?? []
    return tracks.enumerated().map { index, track in
      matches.flatMap { $0.indices.contains(index) ? $0[index] : nil } ?? track
    }
  }
  private var profileLine: String? {
    guard let profile else { return nil }
    let line = [profile.type, profile.country, profile.begin].filter { !$0.isEmpty }
      .joined(separator: " · ")
    return line.isEmpty ? nil : line
  }
  private func loadProfile() async {
    if let value = try? await model.cachedCatalogue(
      key: "profile:" + artistId, load: { try await $0.catalogueProfile(artistId: artistId) })
    {
      profile = value
    }
  }
  private func loadPopular() async {
    guard
      let popular = try? await model.cachedCatalogue(
        key: "popular:" + artistId, load: { try await $0.cataloguePopularity(artistId: artistId) })
    else { return }
    popularity = popular
    let tracks = popular.songs.map(\.track)
    let matches =
      tracks.isEmpty
      ? nil
      : try? await model.cachedCatalogue(key: "popular-matches:" + artistId) {
        try await $0.lookupSongs(tracks)
      }
    popularSongs = Self.songs(popular, matches)
  }
  private func loadAlbums() async {
    do {
      albums = try await model.cachedCatalogue(key: Self.albumsKey(artistId)) {
        try await $0.catalogueGroups(artistId: artistId, offset: 0, kind: "album")
      }
      error = nil
    } catch is CancellationError {} catch { self.error = error.localizedDescription }
  }
  /// The library artist with this name, confirmed against its catalogue identity
  /// when the server can say; the identity is not required offline.
  private func findSaved() async {
    guard let candidate = await model.savedArtist(name: name) else { return }
    do {
      let identity = try await model.cachedCatalogue(key: "identity:" + candidate.id) {
        try await $0.artistIdentity(id: candidate.id)
      }
      if identity.id == artistId { saved = candidate }
    } catch is CancellationError {} catch {
      if model.service == nil { saved = candidate }
    }
  }
}

/// The bottom-of-page link to an artist's complete catalogue.
struct DiscographyLinkLabel: View {
  var body: some View {
    HStack {
      Label("Full discography", systemImage: "square.stack.3d.up")
        .font(.subheadline.weight(.semibold))
      Spacer()
      Image(systemName: "chevron.right").foregroundStyle(.tertiary)
    }
    .padding(.vertical, 12).padding(.horizontal, 14)
    .background(.quaternary.opacity(0.5), in: RoundedRectangle(cornerRadius: 12))
    .contentShape(Rectangle())
  }
}

private struct ReleaseGrid: View {
  let model: AppModel
  let releases: [CatalogueGroup]
  var showType = false
  var body: some View {
    LazyVGrid(columns: cardColumns, spacing: 18) {
      ForEach(releases, id: \.id) { release in
        NavigationLink {
          CatalogueAlbumView(model: model, groupId: release.id, title: release.title)
        } label: {
          CollectionCard(
            model: model, source: .releaseGroup(release.id), title: release.title,
            caption: [showType ? release.type : "", String(release.date.prefix(4))]
              .filter { !$0.isEmpty }.joined(separator: " · "))
        }.buttonStyle(.plain)
      }
    }
  }
}

/// Every release by an artist, filtered by type.
struct CatalogueDiscographyView: View {
  let model: AppModel
  let artistId: String
  let name: String
  @State private var kind = "all"
  @State private var order = "date"
  @State private var releases: [CatalogueGroup]
  @State private var offset: Int
  @State private var total: Int
  @State private var loading = false
  @State private var loaded: Bool
  @State private var error: String?
  init(model: AppModel, artistId: String, name: String) {
    self.model = model
    self.artistId = artistId
    self.name = name
    let page: CatalogueGroups? = model.peekCatalogue(key: "groups:\(artistId):all:0")
    _releases = State(initialValue: page?.releases ?? [])
    _offset = State(initialValue: page.map { $0.offset + $0.releases.count } ?? 0)
    _total = State(initialValue: page?.total ?? 0)
    _loaded = State(initialValue: page != nil)
  }
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        HStack {
          Text(kindLabel).font(.title3.weight(.bold))
          Spacer()
          Menu {
            Picker("Release type", selection: $kind) {
              Text("All releases").tag("all")
              Text("Albums").tag("album")
              Text("Singles").tag("single")
              Text("EPs").tag("ep")
              Text("Other").tag("other")
            }
            Picker("Order", selection: $order) {
              Text("Newest first").tag("date")
              Text("Title").tag("title")
            }
          } label: {
            Label("Filter", systemImage: "line.3.horizontal.decrease.circle")
              .font(PigType.footnote)
          }
        }
        if releases.isEmpty {
          CatalogueStatus(loading: loading, loaded: loaded, empty: true, error: error) {
            Task { await load(reset: true) }
          }
        }
        ReleaseGrid(model: model, releases: orderedReleases, showType: true)
        if offset < total {
          Button("Show more releases") { Task { await load(reset: false) } }.disabled(loading)
            .buttonStyle(ChipStyle(selected: false)).frame(maxWidth: .infinity)
        }
      }.padding(.horizontal).padding(.bottom, 24)
    }
    .pigCanvas().navigationTitle(name).navigationBarTitleDisplayMode(.inline)
    .task(id: kind) { await load(reset: true) }
  }
  private var kindLabel: String {
    ["all": "All releases", "album": "Albums", "single": "Singles", "ep": "EPs", "other": "Other"][
      kind] ?? "All releases"
  }
  private var orderedReleases: [CatalogueGroup] {
    releases.sorted {
      order == "title"
        ? $0.title.localizedStandardCompare($1.title) == .orderedAscending
        : ($0.date, $0.title) > ($1.date, $1.title)
    }
  }
  private func key(_ kind: String, _ offset: Int) -> String { "groups:\(artistId):\(kind):\(offset)" }
  private func load(reset: Bool) async {
    guard reset || !loading else { return }
    let selectedKind = kind
    let next = reset ? 0 : offset
    if reset {
      // Show what this filter showed before, if anything, while it refreshes.
      let page: CatalogueGroups? = model.peekCatalogue(key: key(selectedKind, 0))
      releases = page?.releases ?? []
      offset = page.map { $0.offset + $0.releases.count } ?? 0
      total = page?.total ?? 0
      loaded = page != nil
    }
    loading = true
    error = nil
    defer { if kind == selectedKind { loading = false } }
    do {
      let page = try await model.cachedCatalogue(key: key(selectedKind, next)) {
        try await $0.catalogueGroups(
          artistId: artistId, offset: next, kind: selectedKind == "all" ? nil : selectedKind)
      }
      try Task.checkCancellation()
      guard kind == selectedKind else { return }
      releases = reset ? page.releases : releases + page.releases
      offset = page.offset + page.releases.count
      total = page.releases.isEmpty ? offset : page.total
      loaded = true
    } catch is CancellationError {} catch {
      if kind == selectedKind { self.error = error.localizedDescription }
    }
  }
}

/// An album from the catalogue opens its most likely edition straight away; the
/// other editions are offered at the bottom of that page.
struct CatalogueAlbumView: View {
  let model: AppModel
  let groupId: String
  let title: String
  @State private var editions: CatalogueEditions?
  @State private var error: String?
  init(model: AppModel, groupId: String, title: String) {
    self.model = model
    self.groupId = groupId
    self.title = title
    _editions = State(initialValue: model.peekCatalogue(key: "editions:\(groupId):0"))
  }
  var body: some View {
    Group {
      if let first = editions?.editions.first {
        CatalogueReleaseView(
          model: model, releaseId: first.id, title: first.title, groupId: groupId,
          editionCount: editions?.total ?? 1
        ).id(first.id)
      } else {
        List {
          CatalogueStatus(
            loading: editions == nil && error == nil, loaded: editions != nil, empty: true,
            error: error
          ) { Task { await load() } }
        }.pigCanvas().navigationTitle(title)
      }
    }
    .task { await load() }
  }
  private func load() async {
    error = nil
    do {
      // Editions arrive ranked; the first is the recommended one.
      editions = try await model.cachedCatalogue(key: "editions:\(groupId):0") {
        try await $0.catalogueEditions(groupId: groupId, offset: 0)
      }
    } catch is CancellationError {} catch { self.error = error.localizedDescription }
  }
}

struct CatalogueEditionsView: View {
  let model: AppModel
  let groupId: String
  let title: String
  @State private var editions: [CatalogueEdition] = []
  @State private var offset = 0
  @State private var total = 0
  @State private var loading = false
  @State private var loaded = false
  @State private var error: String?
  var body: some View {
    List {
      CatalogueStatus(loading: loading, loaded: loaded, empty: editions.isEmpty, error: error) {
        Task { await load(reset: !loaded) }
      }
      ForEach(Array(editions.enumerated()), id: \.offset) { _, edition in
        NavigationLink {
          CatalogueReleaseView(model: model, releaseId: edition.id, title: edition.title)
        } label: {
          HStack(spacing: 12) {
          ArtworkThumb(model: model, source: .release(edition.id), title: edition.title, size: 52)
          VStack(alignment: .leading) {
            Text(edition.title)
            Text(
              [edition.date, edition.country, edition.formats.joined(separator: ", ")]
                .filter { !$0.isEmpty }.joined(separator: " · ")
            )
            .font(PigType.caption).foregroundStyle(.secondary)
            if !edition.description.isEmpty { Text(edition.description).font(PigType.caption) }
            Text("\(edition.trackCount) songs · \(edition.status)").font(PigType.caption)
              .foregroundStyle(.secondary)
          }
          }
        }
      }
      if offset < total {
        Button("Load more editions") { Task { await load(reset: false) } }.disabled(loading)
      }
    }.pigCanvas().navigationTitle(title).task { await load(reset: true) }
  }
  private func load(reset: Bool) async {
    guard !loading else { return }
    loading = true
    error = nil
    defer { loading = false }
    let next = reset ? 0 : offset
    do {
      let page = try await model.cachedCatalogue(key: "editions:\(groupId):\(next)") {
        try await $0.catalogueEditions(groupId: groupId, offset: next)
      }
      editions = reset ? page.editions : editions + page.editions
      offset = page.offset + page.editions.count
      total = page.editions.isEmpty ? offset : page.total
      loaded = true
    } catch is CancellationError {} catch { self.error = error.localizedDescription }
  }
}

struct CatalogueReleaseView: View {
  let model: AppModel
  let releaseId: String
  let title: String
  /// Set when this edition was chosen for an album, to offer its other editions.
  let groupId: String?
  let editionCount: Int
  @State private var release: CatalogueRelease?
  @State private var showingArtist = false
  @State private var requesting = false
  @State private var requestFailure: String?
  @State private var loading = false
  @State private var error: String?
  @Environment(\.colorScheme) private var scheme
  init(
    model: AppModel, releaseId: String, title: String, groupId: String? = nil,
    editionCount: Int = 1
  ) {
    self.model = model
    self.releaseId = releaseId
    self.title = title
    self.groupId = groupId
    self.editionCount = editionCount
    _release = State(initialValue: model.peekCatalogue(key: "release:" + releaseId))
  }
  var body: some View {
    List {
      if release == nil {
        CatalogueStatus(loading: loading, loaded: false, empty: true, error: error) {
          Task { await load() }
        }
      } else if release?.songs.isEmpty == true {
        Text("No catalogue results.").foregroundStyle(.secondary)
      }
      if let release {
        Section {
          DetailHeader(
            model: model, source: .release(releaseId), eyebrow: "ALBUM", title: release.title,
            artist: release.artist,
            openArtist: release.artistId == nil ? nil : { showingArtist = true })
          let missing = release.songs.filter {
            $0.availability != "in_library" && $0.availability != "requested"
          }.map(\.track)
          HStack(spacing: 10) {
            PlayCapsule { model.play(release.songs.map(\.track)) }
              .disabled(release.songs.isEmpty)
            RoundIcon(label: "Shuffle", systemImage: "shuffle") {
              model.play(release.songs.map(\.track).shuffled())
            }.disabled(release.songs.isEmpty)
            // The request is shown only by its mark: sending, then the song
            // states (clock = requested), or a warning that retries.
            if requesting {
              ProgressView().frame(width: 40, height: 40).accessibilityLabel("Sending request")
            } else if let requestFailure {
              RoundIcon(label: "Request failed: \(requestFailure). Try again",
                systemImage: "exclamationmark.circle") { Task { await request(missing) } }
              .foregroundStyle(PigBrand.danger(scheme))
            } else if !missing.isEmpty {
              RoundIcon(label: "Add or request album", systemImage: "plus") {
                Task { await request(missing) }
              }
              .disabled(!model.canMutate || missing.count > 500)
            } else if release.songs.contains(where: { $0.availability == "requested" }) {
              RoundIconLabel(systemImage: "clock").accessibilityLabel("Requested")
            }
            Spacer()
          }.buttonStyle(.plain)
        }
        .listRowSeparator(.hidden)
        Section {
          ForEach(Array(release.songs.enumerated()), id: \.offset) { index, song in
            SongRow(model: model, track: track(song), number: index + 1) {
              model.play(release.songs.map(\.track), at: index)
            }
          }
        } footer: {
          Text(
            "Household songs need adding to your library before they play from the server. Other catalogue songs use experimental streaming. Adding or requesting music is a separate action."
          )
        }
        if let groupId, editionCount > 1 {
          Section {
            NavigationLink {
              CatalogueEditionsView(model: model, groupId: groupId, title: release.title)
            } label: {
              Label(
                "Other versions of this album (\(editionCount - 1))", systemImage: "square.stack")
            }
          }
        }
      }
    }
    .pigCanvas().navigationTitle(release?.title ?? title)
    .navigationDestination(isPresented: $showingArtist) {
      if let release, let artistId = release.artistId {
        CatalogueArtistView(model: model, artistId: artistId, name: release.artist)
      }
    }
    .task { await load() }
  }
  private func request(_ tracks: [Track]) async {
    guard !requesting else { return }
    requesting = true
    requestFailure = nil
    defer { requesting = false }
    do {
      _ = try await model.performPersonal { try await $0.requestMusic(tracks) }
      await load()
    } catch is CancellationError {} catch { requestFailure = error.localizedDescription }
  }
  private func track(_ song: CatalogueSong) -> Track {
    var track = song.track
    track.serverState =
      switch song.availability {
      case "in_library": "in_library"
      case "household_available": "household_available"
      case "requested": "requested"
      default: "not_in_library"
      }
    return track
  }
  private func load() async {
    guard !loading else { return }
    loading = true
    error = nil
    defer { loading = false }
    do {
      release = try await model.cachedCatalogue(key: "release:" + releaseId) {
        try await $0.catalogueRelease(releaseId: releaseId)
      }
    } catch is CancellationError {} catch { self.error = error.localizedDescription }
  }
}

private struct CatalogueStatus: View {
  let loading: Bool
  let loaded: Bool
  let empty: Bool
  let error: String?
  let retry: () -> Void
  var body: some View {
    if loading { ProgressView("Loading catalogue…") }
    if let error {
      Text(error).foregroundStyle(.secondary)
      Button("Try again", action: retry).disabled(loading)
    } else if loaded && empty {
      Text("No catalogue results.").foregroundStyle(.secondary)
    }
  }
}
