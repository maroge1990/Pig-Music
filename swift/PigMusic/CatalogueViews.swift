import PigBrand
import PigDomain
import SwiftUI
import UIKit

struct CatalogueArtistView: View {
  let model: AppModel
  let artistId: String
  let name: String
  @State private var kind = "all"
  @State private var order = "date"
  @State private var profile: CatalogueProfile?
  @State private var popularity: CataloguePopularity?
  @State private var popularSongs: [Track] = []
  @State private var portrait: UIImage?
  @State private var releases: [CatalogueGroup] = []
  @State private var offset = 0
  @State private var total = 0
  @State private var loading = false
  @State private var loaded = false
  @State private var error: String?
  var body: some View {
    List {
      if let portrait {
        Image(uiImage: portrait).resizable().scaledToFit().frame(
          maxWidth: .infinity, maxHeight: 260
        ).accessibilityHidden(true)
      }
      if let profile {
        if !profile.description.isEmpty { Text(profile.description).font(PigType.subhead) }
        Text(
          [profile.type, profile.country, profile.begin, profile.end].filter { !$0.isEmpty }.joined(
            separator: " · ")
        ).font(PigType.caption)
      }
      if !popularSongs.isEmpty {
        Section("Popular songs") {
          ForEach(popularSongs) { track in
            SongButton(model: model, track: track) {
              model.play(
                popularSongs, at: popularSongs.firstIndex(where: { $0.id == track.id }) ?? 0)
            }
          }
        }
      }
      if let popular = popularity, !popular.albums.isEmpty {
        Section("Popular albums") {
          ForEach(popular.albums) { release in
            NavigationLink(release.title) {
              CatalogueEditionsView(model: model, groupId: release.id, title: release.title)
            }
          }
        }
      }
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
      NavigationLink("Artist requests and monitoring") {
        ArtistAcquisitionView(model: model, artistId: artistId)
      }
      CatalogueStatus(loading: loading, loaded: loaded, empty: releases.isEmpty, error: error) {
        Task { await load(reset: !loaded) }
      }
      ForEach(orderedReleases, id: \.id) { release in
        NavigationLink {
          CatalogueEditionsView(model: model, groupId: release.id, title: release.title)
        } label: {
          VStack(alignment: .leading) {
            Text(release.title)
            Text([release.type, release.date].filter { !$0.isEmpty }.joined(separator: " · "))
              .font(PigType.caption).foregroundStyle(.secondary)
          }
        }
      }
      if offset < total {
        Button("Load more releases") { Task { await load(reset: false) } }.disabled(loading)
      }
    }.navigationTitle(name).task(id: kind) { await load(reset: true) }.task { await enrich() }
  }
  private var orderedReleases: [CatalogueGroup] {
    releases.sorted {
      order == "title"
        ? $0.title.localizedStandardCompare($1.title) == .orderedAscending
        : ($0.date, $0.title) > ($1.date, $1.title)
    }
  }
  private func enrich() async {
    portrait = await model.artistArtwork(id: artistId)
    profile = try? await model.cachedCatalogue(key: "profile:" + artistId) {
      try await $0.catalogueProfile(artistId: artistId)
    }
    do {
      let popular = try await model.cachedCatalogue(key: "popular:" + artistId) {
        try await $0.cataloguePopularity(artistId: artistId)
      }
      popularity = popular
      let tracks = popular.songs.map(\.track)
      if !tracks.isEmpty {
        let matches = try? await model.cachedCatalogue(key: "popular-matches:" + artistId) {
          try await $0.lookupSongs(tracks)
        }
        popularSongs = tracks.enumerated().map { index, track in
          matches.flatMap { $0.indices.contains(index) ? $0[index] : nil } ?? track
        }
      }
    } catch {}

  }
  private func load(reset: Bool) async {
    guard reset || !loading else { return }
    let selectedKind = kind
    let next = reset ? 0 : offset
    if reset {
      releases = []
      offset = 0
      total = 0
      loaded = false
    }
    loading = true
    error = nil
    defer { if kind == selectedKind { loading = false } }
    do {
      let page = try await model.cachedCatalogue(key: "groups:\(artistId):\(selectedKind):\(next)")
      {
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
      if offset < total {
        Button("Load more editions") { Task { await load(reset: false) } }.disabled(loading)
      }
    }.navigationTitle(title).task { await load(reset: true) }
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
  @State private var release: CatalogueRelease?
  @State private var requesting = false
  @State private var requestMessage: String?
  @State private var loading = false
  @State private var error: String?
  var body: some View {
    List {
      CatalogueStatus(
        loading: loading, loaded: release != nil, empty: release?.songs.isEmpty ?? true,
        error: error
      ) {
        Task { await load() }
      }
      if let release {
        Section {
          Text(release.artist).font(PigType.headline)
          Button("Play album", systemImage: "play.fill") { model.play(release.songs.map(\.track)) }
            .disabled(release.songs.isEmpty)
          let missing = release.songs.filter {
            $0.availability != "in_library" && $0.availability != "requested"
          }.map(\.track)
          if !missing.isEmpty {
            Button("Add or request album", systemImage: "plus.circle") {
              Task { await request(missing) }
            }
            .disabled(requesting || !model.canMutate || missing.count > 500)
          }
          if requesting { ProgressView("Sending request…") }
          if let requestMessage { Text(requestMessage).font(PigType.footnote) }
          Text(
            "Add household songs to your library to stream the server file. Other catalogue songs use experimental streaming; an unavailable provider will report a playback error. Adding or requesting music is a separate action."
          )
          .font(PigType.footnote).foregroundStyle(.secondary)
        }
        ForEach(Array(release.songs.enumerated()), id: \.offset) { index, song in
          VStack(alignment: .leading) {
            SongButton(model: model, track: song.track) {
              model.play(release.songs.map(\.track), at: index)
            }
            Text(availability(song.availability)).font(PigType.caption).foregroundStyle(.secondary)
          }
        }
      }
    }.navigationTitle(release?.title ?? title).task { await load() }
  }
  private func request(_ tracks: [Track]) async {
    guard !requesting else { return }
    requesting = true
    defer { requesting = false }
    do {
      let result = try await model.performPersonal { try await $0.requestMusic(tracks) }
      requestMessage =
        "Server confirmed: \(result.created) new, \(result.existing) existing, \(result.skipped) skipped."
      if !result.downloadsEnabled {
        requestMessage! += " Server downloads are disabled; requests will wait."
      }
      await load()
    } catch is CancellationError {} catch { requestMessage = error.localizedDescription }
  }
  private func availability(_ state: String) -> String {
    switch state {
    case "in_library": "In your library"
    case "household_available": "Available in household"
    case "requested": "Requested"
    default: "Catalogue song"
    }
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
