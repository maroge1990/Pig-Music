import PigBrand
import PigDomain
import SwiftUI

struct HomeView: View {
  @Bindable var model: AppModel
  var body: some View {
    List {
      Section("Recently added") {
        feedStatus(.recent)
        if let content = model.homeContent[.recent] {
          ForEach(content.albums) { album in
            NavigationLink {
              AlbumView(model: model, album: album)
            } label: {
              AlbumRow(model: model, album: album)
            }
          }
          if content.albums.isEmpty {
            Text("Albums you add will appear here.").foregroundStyle(.secondary)
          }
        }
      }
      discovery(.popular, title: "Popular")
      discovery(.recommended, title: "Recommended")
    }
    .navigationTitle("Home")
    .task(id: model.artworkNamespace) { await model.refreshHome() }
    .refreshable {
      await model.refresh()
      await model.refreshHome(force: true)
    }
    .toolbar {
      Button("Refresh", systemImage: "arrow.clockwise") {
        Task { await model.refreshHome(force: true) }
      }.disabled(!model.homeLoading.isEmpty)
    }
  }

  @ViewBuilder private func feedStatus(_ section: HomeSection) -> some View {
    if model.homeLoading.contains(section) { ProgressView("Loading…") }
    if let error = model.homeErrors[section] {
      Text(error).font(PigType.footnote).foregroundStyle(.secondary)
      Button("Try again") { Task { await model.refreshHome(force: true) } }
        .disabled(!model.homeLoading.isEmpty)
    }
  }

  @ViewBuilder private func discovery(_ section: HomeSection, title: String) -> some View {
    Section(model.homeContent[section]?.feed?.title ?? title) {
      feedStatus(section)
      if let feed = model.homeContent[section]?.feed {
        Text(feed.source).font(PigType.caption).foregroundStyle(.secondary)
        if feed.unavailable || feed.state == .unavailable {
          Text("Discovery is temporarily unavailable. Your saved library is still available.")
            .foregroundStyle(.secondary)
        } else if feed.state == .preparing {
          Text("The server is preparing this feed. Refresh shortly.").foregroundStyle(.secondary)
        } else if feed.state == .noSeeds {
          Text("Add some artists to your library to get recommendations.").foregroundStyle(
            .secondary)
        }
        ForEach(feed.artists) { item in
          NavigationLink {
            CatalogueArtistView(model: model, artistId: item.id, name: item.name)
          } label: {
            discoveryRow(item, symbol: "person.fill")
          }
        }
        ForEach(feed.albums) { item in
          NavigationLink {
            CatalogueEditionsView(model: model, groupId: item.id, title: item.name)
          } label: {
            discoveryRow(item, symbol: "square.stack")
          }
        }
        ForEach(Array(feed.songs.enumerated()), id: \.offset) { _, item in
          if let releaseId = item.releaseId {
            NavigationLink {
              CatalogueReleaseView(model: model, releaseId: releaseId, title: item.album)
            } label: {
              discoveryRow(item, symbol: "music.note")
            }
          } else if let track = item.playbackTrack {
            SongButton(model: model, track: track) { model.play([track]) }
          }
        }
        if feed.state == .ready && feed.artists.isEmpty && feed.albums.isEmpty && feed.songs.isEmpty
        {
          Text("No discoveries yet. Try again later.").foregroundStyle(.secondary)
        }
      }
    }
  }

  private func discoveryRow(_ item: DiscoveryItem, symbol: String) -> some View {
    HStack {
      Image(systemName: symbol).frame(width: 32).foregroundStyle(.secondary).accessibilityHidden(
        true)
      VStack(alignment: .leading) {
        Text(item.name)
        if item.kind != .artists {
          Text(item.artist).font(PigType.subhead).foregroundStyle(.secondary)
        }
        if let reason = item.reason {
          Text(reason).font(PigType.caption).foregroundStyle(.secondary)
        }
      }
    }
  }
}
