import AVKit
import PigBrand
import PigDomain
import PigPlayback
import SwiftUI

struct LibraryView: View {
  @Bindable var model: AppModel
  var body: some View {
    List {
      if let message = model.message { Section { Text(message).font(PigType.footnote) } }
      Section {
        NavigationLink("Songs · \(model.songCount)") { SongsView(model: model) }
        NavigationLink("Albums") { AlbumsView(model: model) }
        NavigationLink("On this device") { DownloadsView(model: model) }
        if model.watch?.supported == true {
          NavigationLink("Apple Watch") { WatchDownloadsView(model: model) }
        }
        NavigationLink("Create or import playlists") { PlaylistToolsView(model: model) }
        NavigationLink("Music requests") { RequestsView(model: model) }
        NavigationLink("Artists") {
          List {
            LibrarySortPicker(
              model: model, collection: .artists, selected: model.artistSort, artist: false)
            ForEach(model.artists) { artist in
              NavigationLink(artist.name) { SavedArtistView(model: model, artist: artist) }
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
              : "Sync to see your saved music, or search for songs and albums to add."
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
      LibrarySortPicker(model: model, collection: .tracks, selected: model.songSort)
      Button("Shuffle all songs", systemImage: "shuffle") { Task { await model.shuffleLibrary() } }
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
      LibrarySortPicker(model: model, collection: .albums, selected: model.albumSort)
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
        Button("Send to Apple Watch", systemImage: "applewatch") {
          Task { await model.watch?.enqueue(tracks) }
        }.disabled(tracks.isEmpty)
        Button("Download originals", systemImage: "arrow.down.circle") {
          Task { await model.download(tracks) }
        }.disabled(tracks.isEmpty)
        Button("Download AAC copies") { Task { await model.download(tracks, quality: "aac") } }
          .disabled(tracks.isEmpty)
      }
      ForEach(Array(tracks.enumerated()), id: \.element.id) { index, song in
        SongButton(model: model, track: song) { model.play(tracks, at: index) }
      }
    }.navigationTitle(album.title).task(id: album.id) { tracks = await model.albumTracks(album) }
  }
}

struct SongButton: View {
  let model: AppModel
  let track: Track
  let play: () -> Void
  @Environment(\.colorScheme) private var scheme
  private var current: Bool { model.player.queue.current?.track.id == track.id }
  var body: some View {
    Button {
      if track.serverState == "household_available" { model.actionTrack = track } else { play() }
    } label: {
      HStack {
        if current {
          Capsule().fill(PigBrand.accent(scheme)).frame(width: 4, height: 28)
            .accessibilityHidden(true)
        }
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
          track.serverState == "household_available"
            ? "Add from household"
            : (track.serverState == "not_in_library" ? "Remote streaming" : "On the server"))
      }.frame(minHeight: 44)
    }.listRowBackground(
      PigBrand.surface(scheme).overlay {
        if current { PigBrand.accent(scheme).opacity(0.14) }
      }
    )
    .accessibilityValue(current ? "Current song" : "")
    .accessibilityLabel(
      "\(track.serverState == "household_available" ? "Add" : "Play") \(track.title) by \(track.artist). \(track.serverState == "not_in_library" ? "Remote streaming" : "On the server")."
    )
    .contextMenu {
      Button("Song actions…", systemImage: "ellipsis.circle") { model.actionTrack = track }
    }
    .accessibilityAction(named: "Song actions") { model.actionTrack = track }
  }
}

struct AccountView: View {
  @Bindable var model: AppModel
  var body: some View {
    Form {
      Section("Your account") {
        Text(model.person?.displayName ?? "")
        Text(model.server).font(PigType.footnote).textSelection(.enabled)
        NavigationLink("Appearance") { PreferencesView(model: model) }
        NavigationLink("Password") { PasswordView(model: model) }
        NavigationLink("Devices and sessions") { SessionsView(model: model) }
        NavigationLink("Server quality") { QualityView(model: model) }
        NavigationLink("Personal Plex") { PlexView(model: model) }
        NavigationLink("Pending edits (\(model.pendingEdits.count))") {
          PendingEditsView(model: model)
        }
      }
      Section("Library") {
        Text("\(model.songCount) cached songs")
        Button("Sync now") { Task { await model.refresh() } }.disabled(model.syncing)
      }
      Section("Playback") {
        Toggle(
          "Seamless playback",
          isOn: Binding(
            get: { model.player.seamlessEnabled }, set: { model.player.seamlessEnabled = $0 }))
        if model.player.seamlessEnabled {
          Toggle(
            "Crossfade",
            isOn: Binding(
              get: { model.player.crossfadeEnabled }, set: { model.player.crossfadeEnabled = $0 }))
          Text(
            "Blends unrelated songs for three seconds and preserves continuous album order. Changes apply to the next queue."
          ).font(PigType.footnote)
        }
        Text(
          "Seamless playback may take longer to start while it prepares songs. Turn it off to use streaming if a song cannot be prepared. Changing modes stops playback."
        ).font(PigType.footnote)
      }
      Section {
        Button("Sign out", role: .destructive) { Task { await model.signOut() } }.disabled(
          model.busy || model.mutationActive)
      }
      if let message = model.message { Section { Text(message).font(PigType.footnote) } }
    }.navigationTitle("Account")
  }
}

struct MiniPlayer: View {
  @Bindable var model: AppModel
  private var player: PlayerController { model.player }
  let open: () -> Void
  @Environment(\.colorScheme) private var scheme
  var body: some View {
    HStack {
      ArtworkView(model: model, sha: player.queue.current?.track.coverSha, size: 44)
      Button(action: open) {
        VStack(alignment: .leading) {
          Text(player.queue.current?.track.title ?? "").lineLimit(1)
          Text(player.queue.current?.track.artist ?? "").font(PigType.caption).foregroundStyle(
            PigBrand.secondary(scheme))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }
      if player.preparing { ProgressView().accessibilityLabel("Preparing audio") }
      Button(action: player.toggle) {
        Image(systemName: player.wantsPlayback ? "pause.fill" : "play.fill").frame(
          minWidth: 44, minHeight: 44)
      }.accessibilityLabel(player.wantsPlayback ? "Pause" : "Play")
      Button(action: player.next) {
        Image(systemName: "forward.end.fill").frame(minWidth: 44, minHeight: 44)
      }.accessibilityLabel("Next song")
    }.padding(.horizontal, 16).padding(.vertical, 8)
      .foregroundStyle(PigBrand.text(scheme)).tint(PigBrand.accent(scheme))
      .pigFloatingControls().padding(.horizontal, 8).padding(.bottom, 4)
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
          .pigContentCorners().frame(maxWidth: .infinity).padding(.vertical, 20)
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
              Image(systemName: player.wantsPlayback ? "pause.circle.fill" : "play.circle.fill")
                .font(
                  .largeTitle
                ).frame(minWidth: 60, minHeight: 60)
            }.accessibilityLabel(player.wantsPlayback ? "Pause" : "Play")
            Button(action: player.next) {
              Image(systemName: "forward.end.fill").frame(minWidth: 44, minHeight: 44)
            }.accessibilityLabel("Next song")
          }
          if player.preparing { ProgressView("Preparing audio…").font(PigType.footnote) }
          HStack {
            Button(player.shuffled ? "Shuffle on" : "Shuffle", systemImage: "shuffle") {
              player.toggleShuffle()
            }
            Picker(
              "Repeat",
              selection: Binding(get: { player.repeatMode }, set: { player.repeatMode = $0 })
            ) {
              Text("Off").tag(PlaybackRepeat.off)
              Text("All").tag(PlaybackRepeat.all)
              Text("One").tag(PlaybackRepeat.one)
            }
          }
          if let error = player.error {
            Text(error).font(PigType.footnote).foregroundStyle(Color("PigDanger"))
            HStack {
              Button("Retry") { player.retry() }
              Button("Skip song") { player.next() }
              if player.seamlessEnabled {
                Button("Use streaming") { player.retry(streaming: true) }
              }
            }
          }
          NavigationLink("Edit full queue") { QueueEditorView(player: player) }
          Text("Up next").font(PigType.headline).frame(maxWidth: .infinity, alignment: .leading)
          ForEach(player.queue.items.dropFirst(player.queue.index + 1).prefix(50)) { item in
            HStack {
              Text(item.track.title).frame(maxWidth: .infinity, alignment: .leading)
              Menu("Queue actions", systemImage: "ellipsis") {
                Button("Move earlier") { player.moveUpcoming(item.id, by: -1) }
                Button("Move later") { player.moveUpcoming(item.id, by: 1) }
                Button("Remove from queue", role: .destructive) { player.removeUpcoming(item.id) }
              }
            }
          }
        }.padding()
      }
      .navigationTitle("Now playing").navigationBarTitleDisplayMode(.inline)
      .toolbar { Button("Done") { dismiss() } }
    }.pigBrandedCanvas()
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

struct QueueEditorView: View {
  @Bindable var player: PlayerController
  var body: some View {
    List {
      if let current = player.queue.current {
        Section("Current song") { Text(current.track.title) }
      }
      Section("Up next") {
        ForEach(player.queue.items.dropFirst(player.queue.index + 1)) { item in
          HStack {
            VStack(alignment: .leading) {
              Text(item.track.title)
              Text(item.track.artist).font(.caption)
            }
            Spacer()
            Menu("Queue actions", systemImage: "ellipsis") {
              Button("Move earlier") { player.moveUpcoming(item.id, by: -1) }
              Button("Move later") { player.moveUpcoming(item.id, by: 1) }
              Button("Remove", role: .destructive) { player.removeUpcoming(item.id) }
            }
          }
        }
      }
    }.navigationTitle("Playback queue")
  }
}

private struct LibrarySortPicker: View {
  let model: AppModel
  let collection: LibraryCollection
  let selected: LibrarySort
  var artist = true
  var body: some View {
    Picker(
      "Sort",
      selection: Binding(
        get: { selected },
        set: { value in
          Task { await model.sortLibrary(collection, by: value) }
        })
    ) {
      Text("Title A–Z").tag(LibrarySort.title)
      Text("Title Z–A").tag(LibrarySort.titleDescending)
      if artist { Text("Artist, then title").tag(LibrarySort.artist) }
    }.disabled(model.loadingMore || model.syncing)
  }
}
