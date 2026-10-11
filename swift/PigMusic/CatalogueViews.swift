import PigBrand
import PigDomain
import SwiftUI

struct CatalogueArtistView: View {
  let model: AppModel
  let artistId: String
  let name: String
  @State private var releases: [CatalogueGroup] = []
  @State private var offset = 0
  @State private var total = 0
  @State private var loading = false
  @State private var loaded = false
  @State private var error: String?
  var body: some View {
    List {
      CatalogueStatus(loading: loading, loaded: loaded, empty: releases.isEmpty, error: error) {
        Task { await load(reset: !loaded) }
      }
      ForEach(Array(releases.enumerated()), id: \.offset) { _, release in
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
    }.navigationTitle(name).task { await load(reset: true) }
  }
  private func load(reset: Bool) async {
    guard !loading else { return }
    loading = true
    error = nil
    defer { loading = false }
    let next = reset ? 0 : offset
    do {
      let page = try await model.readCatalogue {
        try await $0.catalogueGroups(artistId: artistId, offset: next)
      }
      releases = reset ? page.releases : releases + page.releases
      offset = page.offset + page.releases.count
      total = page.releases.isEmpty ? offset : page.total
      loaded = true
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
      let page = try await model.readCatalogue {
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
      release = try await model.readCatalogue {
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
