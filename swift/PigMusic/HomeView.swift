import PigBrand
import PigDomain
import SwiftUI

/// Home, as on the web: recently added albums, recommendations (artists and
/// albums only) and the popular chart, each as a shelf of artwork cards.
struct HomeView: View {
  @Bindable var model: AppModel
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 28) {
        Text("Find your next favourite.").font(PigType.subhead).foregroundStyle(.secondary)
          .padding(.horizontal)
        if let recent = model.homeContent[.recent]?.albums, !recent.isEmpty {
          Shelf(title: "Recently added") {
            ForEach(recent) { album in
              NavigationLink {
                AlbumView(model: model, album: album)
              } label: {
                CollectionCard(
                  model: model, source: album.artworkSource, title: album.title,
                  caption: album.artist
                ).frame(width: 150)
              }.buttonStyle(.plain)
            }
          }
        }
        discovery(.recommended, title: "Recommended for you", songs: false)
        discovery(.popular, title: "Popular", songs: true)
      }.padding(.vertical, 8)
    }
    .navigationTitle("Home")
    .task(id: model.artworkNamespace) { await model.refreshHome() }
    .refreshable {
      await model.refresh()
      await model.refreshHome(force: true)
    }
  }

  @ViewBuilder private func discovery(_ section: HomeSection, title: String, songs: Bool)
    -> some View
  {
    let feed = model.homeContent[section]?.feed
    let heading = feed?.title ?? title
    VStack(alignment: .leading, spacing: 18) {
      if let feed, !feed.artists.isEmpty {
        Shelf(title: heading, caption: feed.source.isEmpty ? nil : feed.source) {
          ForEach(feed.artists) { item in
            NavigationLink {
              CatalogueArtistView(model: model, artistId: item.id, name: item.name)
            } label: {
              CollectionCard(
                model: model, source: .artist(item.id), title: item.name,
                caption: item.reason, circle: true
              ).frame(width: 140)
            }.buttonStyle(.plain)
          }
        }
      }
      if let feed, !feed.albums.isEmpty {
        Shelf(title: feed.artists.isEmpty ? heading : "Albums") {
          ForEach(feed.albums) { item in
            NavigationLink {
              CatalogueEditionsView(model: model, groupId: item.id, title: item.name)
            } label: {
              CollectionCard(
                model: model, source: .releaseGroup(item.id), title: item.name,
                caption: item.artist
              ).frame(width: 150)
            }.buttonStyle(.plain)
          }
        }
      }
      if songs, let feed, !feed.songs.isEmpty {
        VStack(alignment: .leading, spacing: 4) {
          Text("Songs").font(.title3.weight(.bold))
          let tracks = feed.songs.prefix(10).compactMap(\.playbackTrack)
          ForEach(Array(tracks.enumerated()), id: \.offset) { index, track in
            SongRow(model: model, track: track) { model.play(tracks, at: index) }
            Divider()
          }
        }.padding(.horizontal)
      }
      status(section, feed: feed, heading: heading)
    }
  }

  @ViewBuilder private func status(_ section: HomeSection, feed: DiscoveryFeed?, heading: String)
    -> some View
  {
    let empty = feed.map { $0.artists.isEmpty && $0.albums.isEmpty && $0.songs.isEmpty } ?? true
    if empty || model.homeErrors[section] != nil {
      VStack(alignment: .leading, spacing: 6) {
        Text(heading).font(.title3.weight(.bold))
        if model.homeLoading.contains(section) {
          ProgressView("Finding music…")
        } else if let error = model.homeErrors[section] {
          Text(error).font(PigType.footnote).foregroundStyle(.secondary)
          Button("Try again") { Task { await model.refreshHome(force: true) } }
        } else if let feed {
          Text(message(section, feed)).font(PigType.footnote).foregroundStyle(.secondary)
        }
      }.padding(.horizontal)
    }
  }

  private func message(_ section: HomeSection, _ feed: DiscoveryFeed) -> String {
    if feed.state == .preparing { return "Finding what’s popular…" }
    if feed.state == .noSeeds {
      return "Recommendations appear once Pig Music has matched artists in your library."
    }
    if feed.unavailable || feed.state == .unavailable {
      return section == .popular
        ? "Charts are temporarily unavailable." : "Recommendations are temporarily unavailable."
    }
    return "Nothing here yet. Try again later."
  }
}
