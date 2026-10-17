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
        if let mixes = model.homeContent[.mixes]?.mixes, !mixes.isEmpty {
          Shelf(title: "Your mixes", caption: "Familiar favourites. Something new. Made for today.")
          {
            ForEach(mixes) { mix in
              NavigationLink {
                MixDetailView(model: model, mix: mix)
              } label: {
                VStack(alignment: .leading, spacing: 6) {
                  MixArtwork(kind: mix.kind).frame(width: 150, height: 150)
                  Text(mix.title).font(.headline).lineLimit(2)
                  Text(
                    Array(Set(mix.tracks.map(\.artist))).sorted().prefix(3).joined(separator: " · ")
                  )
                  .font(PigType.footnote).foregroundStyle(.secondary).lineLimit(2)
                  Text(
                    "\(mix.tracks.count) \(mix.tracks.count == 1 ? "song" : "songs") · Ready to play"
                  ).font(PigType.footnote)
                    .foregroundStyle(.secondary)
                }.frame(width: 150, alignment: .leading)
              }.buttonStyle(.plain)
            }
          }
        } else {
          VStack(alignment: .leading, spacing: 6) {
            Text("Your mixes").font(.title3.weight(.bold))
            Text(
              model.homeErrors[.mixes]
                ?? (model.homeContent[.mixes]?.mixesPreparing == true
                  ? "Preparing your mixes. They'll appear once their audio is ready."
                  : "Your mixes appear as your library grows. Discoveries are prepared ahead of playback.")
            )
            .font(PigType.footnote).foregroundStyle(.secondary)
          }.padding(.horizontal)
        }
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
              CatalogueAlbumView(model: model, groupId: item.id, title: item.name)
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
      return "Recommendations appear once PigMusic has matched artists in your library."
    }
    if feed.unavailable || feed.state == .unavailable {
      return section == .popular
        ? "Charts are temporarily unavailable." : "Recommendations are temporarily unavailable."
    }
    return "Nothing here yet. Try again later."
  }
}

struct MixDetailView: View {
  @Environment(\.dismiss) private var dismiss
  let model: AppModel
  let mix: PersonalMix
  @State private var hidden: Set<String> = []
  @State private var notice: String?
  @State private var saving = false
  private var tracks: [Track] { mix.tracks.filter { !hidden.contains($0.id) } }
  var body: some View {
    List {
      Section {
        HStack(spacing: 16) {
          MixArtwork(kind: mix.kind).frame(width: 112, height: 112)
          VStack(alignment: .leading, spacing: 6) {
            Text(mix.title).font(.title2.bold())
            Text(mix.reason).font(PigType.footnote).foregroundStyle(.secondary)
            Text(mix.day).font(PigType.footnote).foregroundStyle(.secondary)
          }
        }.listRowBackground(Color.clear)
        Button("Play mix", systemImage: "play.fill") { model.play(tracks) }.disabled(tracks.isEmpty)
        Button("Save this edition", systemImage: "plus") {
          saving = true
          Task {
            do {
              _ = try await model.performPersonal { try await $0.saveMix(mix.id) }
              notice =
                "Playlist saved. Add songs to your library to keep their audio after this mix leaves rotation."
            } catch { notice = error.localizedDescription }
            saving = false
          }
        }.disabled(saving)
        if let notice { Text(notice).font(PigType.footnote) }
      }
      Section {
        ForEach(Array(tracks.enumerated()), id: \.element.id) { index, track in
          SongRow(model: model, track: track.actionTrack) { model.play(tracks, at: index) }
            .swipeActions {
              Button("Hide", role: .destructive) {
                Task {
                  do {
                    try await model.performPersonal { try await $0.hideMixSong(track.id) }
                    hidden.insert(track.id)
                  } catch { notice = error.localizedDescription }
                }
              }
            }
        }
      }
    }.pigCanvas().navigationTitle(mix.title).navigationBarTitleDisplayMode(.inline)
      .toolbar {
        ToolbarItem(placement: .topBarTrailing) {
          Menu {
            Button("Hide this edition", role: .destructive) {
              saving = true
              Task {
                do {
                  try await model.performPersonal { try await $0.hideMix(mix.id) }
                  let current = model.homeContent[.mixes]
                  let updated = HomeContent(
                    mixes: current?.mixes?.filter { $0.id != mix.id },
                    mixesPreparing: current?.mixesPreparing)
                  model.homeContent[.mixes] = updated
                  let archive = model.store
                  dismiss()
                  try? await archive?.cache(updated, key: "home:mixes")
                } catch { notice = error.localizedDescription }
                saving = false
              }
            }.disabled(saving)
          } label: {
            Image(systemName: "ellipsis.circle").accessibilityLabel("Mix options")
          }
        }
      }
  }
}

/// Vector covers use the same five motifs and Pig family colours as the web.
struct MixArtwork: View {
  let kind: String
  var body: some View {
    Canvas { context, size in
      context.scaleBy(x: size.width / 200, y: size.height / 200)
      let pair = PigMixArtwork.colours(kind)
      let ink = GraphicsContext.Shading.color(pair.foreground)
      context.fill(Path(CGRect(x: 0, y: 0, width: 200, height: 200)), with: .color(pair.background))
      if kind == "daily" {
        for rect in [
          CGRect(x: 34, y: 47, width: 86, height: 86), CGRect(x: 80, y: 73, width: 86, height: 86),
        ] {
          context.stroke(Path(ellipseIn: rect), with: ink, lineWidth: 12)
        }
      } else if kind == "artist" {
        context.stroke(
          Path(ellipseIn: CGRect(x: 43, y: 43, width: 114, height: 114)), with: ink, lineWidth: 12)
        var orbit = context
        orbit.translateBy(x: 100, y: 100)
        orbit.rotate(by: .degrees(-35))
        orbit.stroke(
          Path(ellipseIn: CGRect(x: -83, y: -26, width: 166, height: 52)), with: ink, lineWidth: 12)
        context.fill(Path(ellipseIn: CGRect(x: 87, y: 87, width: 26, height: 26)), with: ink)
      } else if kind == "genre" {
        for i in 0..<4 {
          let y = CGFloat(65 + i * 26)
          var wave = Path()
          wave.move(to: CGPoint(x: -10, y: y))
          wave.addQuadCurve(to: CGPoint(x: 100, y: y), control: CGPoint(x: 40, y: y - 60))
          wave.addQuadCurve(to: CGPoint(x: 210, y: y), control: CGPoint(x: 160, y: y + 60))
          context.stroke(wave, with: ink, lineWidth: 12)
        }
      } else if kind == "popular" {
        for i in 0..<4 {
          context.fill(
            Path(CGRect(x: 35 + i * 36, y: 122 - i * 24, width: 20, height: 45 + i * 24)), with: ink
          )
        }
      } else {
        for x in [CGFloat(95), CGFloat(156)] {
          var arrow = Path()
          arrow.move(to: CGPoint(x: x, y: 57))
          arrow.addLine(to: CGPoint(x: x - 53, y: 100))
          arrow.addLine(to: CGPoint(x: x, y: 143))
          arrow.closeSubpath()
          context.fill(arrow, with: ink)
        }
      }
      var line = Path()
      line.move(to: CGPoint(x: 18, y: 182))
      line.addLine(to: CGPoint(x: 182, y: 182))
      context.stroke(line, with: ink, lineWidth: 2)
      context.fill(Path(ellipseIn: CGRect(x: 176, y: 14, width: 10, height: 10)), with: ink)
    }.aspectRatio(1, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: 12))
      .accessibilityHidden(true)
  }
}
