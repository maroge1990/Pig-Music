import AVKit
import PigBrand
import PigDomain
import SwiftUI

struct LibraryView: View {
  @Bindable var model: AppModel
  var body: some View {
    List {
      if let message = model.message { Section { Text(message).font(PigType.footnote) } }
      Section {
        NavigationLink("Songs · \(model.songCount)") { SongsView(model: model) }
        NavigationLink("Albums") { AlbumsView(model: model) }
        NavigationLink("Artists") {
          List {
            ForEach(model.artists) { artist in
              VStack(alignment: .leading) {
                Text(artist.name)
                Text("\(artist.trackCount ?? 0) songs").font(PigType.caption).foregroundStyle(
                  .secondary)
              }
            }
            if model.artists.count < model.artistCount {
              Button("Load more artists") { Task { await model.more(.artists) } }.disabled(
                model.loadingMore || model.syncing)
            }
          }.navigationTitle("Artists")
        }
      }
      if !model.albums.isEmpty {
        Section("Albums") {
          ForEach(model.albums.prefix(6)) { album in
            NavigationLink {
              AlbumView(model: model, album: album)
            } label: {
              AlbumRow(model: model, album: album)
            }
          }
        }
      }
      if !model.playlists.isEmpty {
        Section("Playlists") {
          ForEach(model.playlists) { playlist in
            NavigationLink(playlist.name) { PlaylistView(model: model, playlist: playlist) }
          }
        }
      }
      if model.songCount == 0 {
        ContentUnavailableView(
          "Your library", systemImage: "music.note",
          description: Text(
            model.syncing
              ? "Syncing your music…"
              : "Sync to see your saved music. Add music using the web app while the native client is being built."
          ))
      }
    }
    .navigationTitle("Library")
    .toolbar {
      Button {
        Task { await model.refresh() }
      } label: {
        if model.syncing {
          ProgressView()
        } else {
          Label("Sync", systemImage: "arrow.triangle.2.circlepath")
        }
      }.disabled(model.syncing)
    }
    .refreshable { await model.refresh() }
  }
}

struct SongsView: View {
  @Bindable var model: AppModel
  var body: some View {
    List {
      ForEach(Array(model.songs.enumerated()), id: \.element.id) { index, track in
        SongButton(model: model, track: track) { model.play(model.songs, at: index) }
      }
      if model.songs.count < model.songCount {
        Button("Load more songs") { Task { await model.more(.tracks) } }.disabled(
          model.loadingMore || model.syncing)
      }
    }.navigationTitle("Songs")
  }
}

struct AlbumsView: View {
  @Bindable var model: AppModel
  var body: some View {
    List {
      ForEach(model.albums) { album in
        NavigationLink {
          AlbumView(model: model, album: album)
        } label: {
          AlbumRow(model: model, album: album)
        }
      }
      if model.albums.count < model.albumCount {
        Button("Load more albums") { Task { await model.more(.albums) } }.disabled(
          model.loadingMore || model.syncing)
      }
    }.navigationTitle("Albums")
  }
}

struct AlbumRow: View {
  let model: AppModel
  let album: Album
  var body: some View {
    HStack {
      ArtworkView(model: model, sha: album.coverSha, size: 52)
      VStack(alignment: .leading) {
        Text(album.title)
        Text(album.artist).font(PigType.subhead).foregroundStyle(.secondary)
      }
    }
  }
}

struct AlbumView: View {
  @Bindable var model: AppModel
  let album: Album
  @State private var tracks: [Track] = []
  var body: some View {
    List {
      Section {
        ArtworkView(model: model, sha: album.coverSha, width: 512, size: 220)
          .frame(maxWidth: .infinity)
        Text(album.artist).font(PigType.headline)
        Button("Play album", systemImage: "play.fill") { model.play(tracks) }.disabled(
          tracks.isEmpty)
      }
      ForEach(Array(tracks.enumerated()), id: \.element.id) { index, song in
        SongButton(model: model, track: song) { model.play(tracks, at: index) }
      }
    }.navigationTitle(album.title).task(id: album.id) { tracks = await model.albumTracks(album) }
  }
}

struct PlaylistView: View {
  @Bindable var model: AppModel
  let playlist: Playlist
  private var songs: [Track] {
    (playlist.entries ?? []).map { entry in
      if let saved = entry.savedTrack { return saved }
      var song = Track(
        id: entry.entryId, title: entry.title, artist: entry.artist, album: entry.album,
        duration: entry.duration)
      song.albumArtist = entry.albumArtist
      song.trackNumber = entry.trackNumber
      song.discNumber = entry.discNumber
      song.serverState = "not_in_library"
      song.musicbrainzReleaseId = entry.musicbrainzReleaseId
      song.musicbrainzRecordingId = entry.musicbrainzRecordingId
      return song
    }
  }
  var body: some View {
    List {
      Section {
        Button("Play playlist", systemImage: "play.fill") { model.play(songs) }.disabled(
          songs.isEmpty)
      }
      ForEach(Array((playlist.entries ?? []).enumerated()), id: \.element.entryId) { index, _ in
        SongButton(model: model, track: songs[index]) { model.play(songs, at: index) }
      }
    }.navigationTitle(playlist.name)
  }
}

struct SongButton: View {
  let model: AppModel
  let track: Track
  let play: () -> Void
  var body: some View {
    Button(action: play) {
      HStack {
        ArtworkView(model: model, sha: track.coverSha, size: 44)
        VStack(alignment: .leading) {
          Text(track.title).foregroundStyle(.primary)
          Text(track.artist).font(PigType.subhead).foregroundStyle(.secondary)
        }
        Spacer()
        Image(
          systemName: track.serverState == "not_in_library"
            ? "antenna.radiowaves.left.and.right" : "icloud"
        ).foregroundStyle(.secondary).accessibilityLabel(
          track.serverState == "not_in_library" ? "Remote streaming" : "On the server")
      }.frame(minHeight: 44)
    }.accessibilityLabel(
      "Play \(track.title) by \(track.artist). \(track.serverState == "not_in_library" ? "Remote streaming" : "On the server")."
    )
  }
}

struct SearchView: View {
  @Bindable var model: AppModel
  @State private var query = ""
  @State private var results: [Track] = []
  var body: some View {
    List(results) { song in SongButton(model: model, track: song) { model.play([song]) } }
      .navigationTitle("Search").searchable(text: $query, prompt: "Search your cached songs")
      .task(id: query) {
        do {
          try await Task.sleep(for: .milliseconds(200))
          try Task.checkCancellation()
        } catch { return }
        let found = await model.search(query)
        guard !Task.isCancelled else { return }
        results = found
      }
      .overlay { if results.isEmpty { ContentUnavailableView.search(text: query) } }
  }
}

struct AccountView: View {
  @Bindable var model: AppModel
  var body: some View {
    Form {
      Section("Your account") {
        Text(model.person?.displayName ?? "")
        Text(model.server).font(PigType.footnote).textSelection(.enabled)
      }
      Section("Library") {
        Text("\(model.songCount) cached songs")
        Button("Sync now") { Task { await model.refresh() } }.disabled(model.syncing)
      }
      Section {
        Button("Sign out", role: .destructive) { Task { await model.signOut() } }.disabled(
          model.busy)
      }
      if let message = model.message { Section { Text(message).font(PigType.footnote) } }
    }.navigationTitle("Account")
  }
}

struct MiniPlayer: View {
  @Bindable var model: AppModel
  private var player: PlayerController { model.player }
  let open: () -> Void
  var body: some View {
    HStack {
      ArtworkView(model: model, sha: player.queue.current?.track.coverSha, size: 44)
      Button(action: open) {
        VStack(alignment: .leading) {
          Text(player.queue.current?.track.title ?? "").lineLimit(1)
          Text(player.queue.current?.track.artist ?? "").font(PigType.caption).foregroundStyle(
            .white.opacity(0.75))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      Button(action: player.toggle) {
        Image(systemName: player.playing ? "pause.fill" : "play.fill").frame(
          minWidth: 44, minHeight: 44)
      }.accessibilityLabel(player.playing ? "Pause" : "Play")
      Button(action: player.next) {
        Image(systemName: "forward.end.fill").frame(minWidth: 44, minHeight: 44)
      }.accessibilityLabel("Next song")
    }.padding(.horizontal).padding(.vertical, 8).foregroundStyle(.white).tint(
      Color(red: 239 / 255, green: 122 / 255, blue: 174 / 255)
    ).background(Color(red: 21 / 255, green: 17 / 255, blue: 26 / 255))
  }
}

struct NowPlayingView: View {
  @Bindable var model: AppModel
  private var player: PlayerController { model.player }
  @Environment(\.dismiss) private var dismiss
  var body: some View {
    NavigationStack {
      ScrollView {
        VStack(spacing: 24) {
          ArtworkView(
            model: model, sha: player.queue.current?.track.coverSha, width: 512, size: 280
          )
          .frame(maxWidth: .infinity).padding(.vertical, 20)
          Text(player.queue.current?.track.title ?? "").font(PigType.title)
          Text(player.queue.current?.track.artist ?? "").font(PigType.headline)
          Slider(
            value: Binding(
              get: { min(player.elapsed, max(1, player.duration)) }, set: { player.seek($0) }),
            in: 0...max(1, player.duration)
          ).accessibilityLabel("Playback position")
          HStack(spacing: 32) {
            Button(action: player.previous) {
              Image(systemName: "backward.end.fill").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("Previous song")
            Button(action: player.toggle) {
              Image(systemName: player.playing ? "pause.circle.fill" : "play.circle.fill").font(
                .largeTitle
              ).frame(minWidth: 60, minHeight: 60)
            }.accessibilityLabel(player.playing ? "Pause" : "Play")
            Button(action: player.next) {
              Image(systemName: "forward.end.fill").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("Next song")
          }
          if let error = player.error { Text(error).font(PigType.footnote).foregroundStyle(.red) }
          Text("Up next").font(PigType.headline).frame(maxWidth: .infinity, alignment: .leading)
          ForEach(player.queue.items.dropFirst(player.queue.index + 1)) { item in
            Text(item.track.title).frame(maxWidth: .infinity, alignment: .leading)
          }
        }.padding()
      }
      .navigationTitle("Now playing").navigationBarTitleDisplayMode(.inline)
      .toolbar { Button("Done") { dismiss() } }
    }.preferredColorScheme(.dark).tint(Color(red: 239 / 255, green: 122 / 255, blue: 174 / 255))
  }
}

struct ArtworkView: View {
  let model: AppModel
  let sha: String?
  var width = 256
  let size: CGFloat
  @State private var image: UIImage?
  private var identity: String {
    "\(model.artworkNamespace)|\(model.artworkRefresh)|\(sha ?? "")|\(width)"
  }
  var body: some View {
    Group {
      if let image {
        Image(uiImage: image).resizable().scaledToFill()
      } else {
        RoundedRectangle(cornerRadius: 8).fill(.secondary.opacity(0.12))
          .overlay {
            Image(systemName: "music.note").font(.system(size: size * 0.35)).foregroundStyle(
              .secondary)
          }
      }
    }
    .frame(width: size, height: size).clipShape(RoundedRectangle(cornerRadius: 8))
    .accessibilityHidden(true)
    .task(id: identity) {
      image = nil
      let loaded = await model.artwork(sha: sha, width: width)
      guard !Task.isCancelled else { return }
      image = loaded
    }
  }
}
