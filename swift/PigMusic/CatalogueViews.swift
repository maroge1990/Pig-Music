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
  @State private var releases: [CatalogueGroup] = []
  @State private var offset = 0
  @State private var total = 0
  @State private var loading = false
  @State private var loaded = false
  @State private var error: String?
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 16) {
        DetailHeader(
          model: model, source: .artist(artistId), eyebrow: "ARTIST", title: name,
          subtitle: profileLine, circle: true)
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
                CatalogueEditionsView(model: model, groupId: release.id, title: release.title)
              } label: {
                CollectionCard(
                  model: model, source: .releaseGroup(release.id), title: release.title,
                  caption: String(release.date.prefix(4))
                ).frame(width: 150)
              }.buttonStyle(.plain)
            }
          }.padding(.horizontal, -16)
        }
        HStack {
          Text("Discography").font(.title3.weight(.bold))
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
            Label(kindLabel, systemImage: "line.3.horizontal.decrease.circle")
              .font(PigType.footnote)
          }
        }
        CatalogueStatus(loading: loading, loaded: loaded, empty: releases.isEmpty, error: error) {
          Task { await load(reset: !loaded) }
        }
        LazyVGrid(columns: cardColumns, spacing: 18) {
          ForEach(orderedReleases, id: \.id) { release in
            NavigationLink {
              CatalogueEditionsView(model: model, groupId: release.id, title: release.title)
            } label: {
              CollectionCard(
                model: model, source: .releaseGroup(release.id), title: release.title,
                caption: [release.type, String(release.date.prefix(4))].filter { !$0.isEmpty }
                  .joined(separator: " · "))
            }.buttonStyle(.plain)
          }
        }
        if offset < total {
          Button("Show more releases") { Task { await load(reset: false) } }.disabled(loading)
            .buttonStyle(ChipStyle(selected: false)).frame(maxWidth: .infinity)
        }
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
    .task(id: kind) { await load(reset: true) }.task { await enrich() }
  }
  private var profileLine: String? {
    guard let profile else { return nil }
    let line = [profile.type, profile.country, profile.begin].filter { !$0.isEmpty }
      .joined(separator: " · ")
    return line.isEmpty ? nil : line
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
  private func enrich() async {
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
          DetailHeader(
            model: model, source: .release(releaseId), eyebrow: "ALBUM", title: release.title,
            subtitle: release.artist)
          let missing = release.songs.filter {
            $0.availability != "in_library" && $0.availability != "requested"
          }.map(\.track)
          HStack(spacing: 10) {
            PlayCapsule { model.play(release.songs.map(\.track)) }
              .disabled(release.songs.isEmpty)
            RoundIcon(label: "Shuffle", systemImage: "shuffle") {
              model.play(release.songs.map(\.track).shuffled())
            }.disabled(release.songs.isEmpty)
            if !missing.isEmpty {
              RoundIcon(label: "Add or request album", systemImage: "plus") {
                Task { await request(missing) }
              }
              .disabled(requesting || !model.canMutate || missing.count > 500)
            }
            Spacer()
          }.buttonStyle(.plain)
          if requesting { ProgressView("Sending request…") }
          if let requestMessage { Text(requestMessage).font(PigType.footnote) }
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
      }
    }.pigCanvas().navigationTitle(release?.title ?? title).task { await load() }
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
