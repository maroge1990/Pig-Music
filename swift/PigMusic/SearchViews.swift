import PigBrand
import PigDomain
import PigSync
import SwiftUI

struct SearchView: View {
  @Bindable var model: AppModel
  @State private var query = ""
  var body: some View {
    Group {
      if let session = model.searchSession {
        SearchResultsView(model: model, session: session)
      } else {
        ProgressView("Opening library…")
      }
    }
    .navigationTitle("Search")
    .searchable(text: $query, prompt: "Songs, albums and artists")
    .task(id: "\(model.artworkNamespace)|\(SearchText.clean(query))") {
      model.searchSession?.clear()
      do {
        try await Task.sleep(for: .milliseconds(200))
        try Task.checkCancellation()
      } catch { return }
      await model.searchSession?.search(query)
    }
    .toolbar {
      Button("Refresh", systemImage: "arrow.clockwise") {
        Task { await model.searchSession?.search(query) }
      }.disabled(SearchText.clean(query).isEmpty)
    }
  }
}

private struct SearchResultsView: View {
  let model: AppModel
  @Bindable var session: SearchSession
  var body: some View {
    List {
      if session.query.isEmpty {
        ContentUnavailableView(
          "Find music", systemImage: "magnifyingglass",
          description: Text("Search your saved library, household music and the catalogue."))
      } else {
        Section("Your library") {
          status(
            loading: session.localLoading, error: session.localError,
            empty: session.tracks.isEmpty && session.albums.isEmpty && session.artists.isEmpty)
          ForEach(session.artists) { artist in
            NavigationLink(artist.name) { SavedArtistView(model: model, artist: artist) }
          }
          ForEach(session.albums) { album in
            NavigationLink {
              AlbumView(model: model, album: album)
            } label: {
              AlbumRow(model: model, album: album)
            }
          }
          ForEach(session.tracks) { song in
            SongButton(model: model, track: song) { model.play([song]) }
          }
          if session.localNext != nil {
            Button("More library results") { Task { await session.moreLocal() } }.disabled(
              session.localLoading)
          }
        }
        if session.onlineEnabled {
          Section("Household songs") {
            status(
              loading: session.householdLoading, error: session.householdError,
              empty: session.household.isEmpty)
            ForEach(session.household) { song in
              SongButton(model: model, track: song) { model.play([song]) }
            }
            if session.householdNext != nil {
              Button("More household results") { Task { await session.moreHousehold() } }.disabled(
                session.householdLoading)
            }
          }
          Section("Catalogue artists") {
            if session.query.count < 2 {
              Text("Enter at least two characters.").foregroundStyle(.secondary)
            } else {
              status(
                loading: session.catalogueLoading, error: session.catalogueError,
                empty: session.catalogue.isEmpty)
              ForEach(session.catalogue) { artist in
                NavigationLink {
                  CatalogueArtistView(model: model, artistId: artist.id, name: artist.name)
                } label: {
                  VStack(alignment: .leading) {
                    Text(artist.name)
                    if !artist.description.isEmpty {
                      Text(artist.description).font(PigType.caption).foregroundStyle(.secondary)
                    }
                  }
                }
              }
              if session.catalogueNext != nil {
                Button("More catalogue artists") { Task { await session.moreCatalogue() } }
                  .disabled(session.catalogueLoading)
              }
            }
          }
        }
      }
    }
  }
  @ViewBuilder private func status(loading: Bool, error: String?, empty: Bool) -> some View {
    if loading { ProgressView("Searching…") }
    if let error { Text(error).font(PigType.footnote).foregroundStyle(.secondary) }
    if !loading && error == nil && empty { Text("No matches").foregroundStyle(.secondary) }
  }
}

struct SavedArtistView: View {
  let model: AppModel
  let artist: Artist
  @State private var identity: ArtistIdentity?
  @State private var identityMessage: String?
  @State private var albums: [Album] = []
  @State private var loading = false
  @State private var more = true
  @State private var error: String?
  var body: some View {
    List {
      if let identity {
        NavigationLink("Explore artist catalogue") {
          CatalogueArtistView(model: model, artistId: identity.id, name: identity.name)
        }
      } else {
        Button("Find artist catalogue") { Task { await identify() } }
        if let identityMessage { Text(identityMessage).font(PigType.footnote) }
      }
      ForEach(albums) { album in
        NavigationLink {
          AlbumView(model: model, album: album)
        } label: {
          AlbumRow(model: model, album: album)
        }
      }
      if loading { ProgressView() }
      if let error { Text(error).font(PigType.footnote) }
      if more { Button("Load albums") { Task { await load() } }.disabled(loading) }
    }.navigationTitle(artist.name).task { if albums.isEmpty { await load() } }
  }
  private func identify() async {
    do {
      identity = try await model.cachedCatalogue(key: "identity:" + artist.id) {
        try await $0.artistIdentity(id: artist.id)
      }
      identityMessage = nil
    } catch { identityMessage = error.localizedDescription }
  }
  private func load() async {
    guard !loading, let store = model.store else { return }
    let namespace = model.artworkNamespace
    loading = true
    error = nil
    defer { loading = false }
    do {
      let found = try await store.albums(artistId: artist.id, offset: albums.count)
      try Task.checkCancellation()
      guard namespace == model.artworkNamespace else { return }
      albums += found
      more = found.count == 100
    } catch is CancellationError {} catch { self.error = error.localizedDescription }
  }
}
