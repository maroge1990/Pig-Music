import PigCompanion
import PigDomain
import PigPlayback
import SwiftUI

@main struct PigMusicWatchApp: App {
  @State private var model = WatchModel()
  @Environment(\.scenePhase) private var scenePhase
  var body: some Scene {
    WindowGroup {
      WatchLibraryView(model: model).task { await model.reload() }
        .onChange(of: scenePhase) { _, phase in
          if phase == .active { Task { await model.reload() } }
        }
    }
    .backgroundTask(.watchConnectivity) { await model.finishBackgroundDelivery() }
  }
}
private struct WatchLibraryView: View {
  @Bindable var model: WatchModel
  var body: some View {
    NavigationStack {
      List {
        if !model.queue.isEmpty { NavigationLink("Now playing") { WatchNowPlaying(model: model) } }
        NavigationLink("Songs on Watch") {
          WatchSongs(model: model, ids: model.manifest.songs.map(\.id), title: "Songs")
        }
        NavigationLink("Albums") {
          List {
            ForEach(model.albums) { album in
              NavigationLink {
                WatchSongs(model: model, ids: album.ids, title: album.title)
              } label: {
                VStack(alignment: .leading) {
                  Text(album.title)
                  Text(album.artist).font(.caption)
                }
              }
            }
          }.navigationTitle("Albums")
        }
        ForEach(model.manifest.collections.filter { !$0.songIds.isEmpty }) { collection in
          NavigationLink(collection.favourites ? "Favourites" : collection.name) {
            WatchSongs(model: model, ids: collection.songIds, title: collection.name)
          }
        }
        NavigationLink("Get music from phone") { WatchPhoneLibrary(model: model) }
        NavigationLink("Phone remote") {
          List {
            Button("Previous", systemImage: "backward.end.fill") {
              Task { await model.send("previous") }
            }
            Button("Play / pause", systemImage: "playpause.fill") {
              Task { await model.send("playPause") }
            }
            Button("Next", systemImage: "forward.end.fill") { Task { await model.send("next") } }
          }.navigationTitle("Phone remote")
        }
        NavigationLink("Storage & sync") {
          List {
            Text("\(model.receipt?.ready.count ?? 0) songs downloaded")
            Text(
              ByteCountFormatter.string(
                fromByteCount: model.receipt?.usedBytes ?? 0, countStyle: .file))
            Text(
              model.link?.reachable == true
                ? "Phone reachable" : "Phone unavailable · offline music still plays")
            Picker(
              "Watch budget",
              selection: Binding(
                get: { Int((model.receipt?.budgetBytes ?? 1_073_741_824) / 1_073_741_824) },
                set: { value in Task { await model.setBudget(value) } })
            ) {
              ForEach([1, 2, 4, 8], id: \.self) { Text("\($0) GB").tag($0) }
            }
            Button("Sync with phone") { Task { await model.send("sync") } }
            Picker("Repeat", selection: $model.repeatMode) {
              Text("Off").tag(PlaybackRepeat.off)
              Text("All").tag(PlaybackRepeat.all)
              Text("One").tag(PlaybackRepeat.one)
            }
            Toggle("Crossfade", isOn: $model.crossfade)
            Text(
              "Gapless playback preserves continuous albums. Crossfade blends other songs over 3 seconds. Changes apply to the next queue."
            ).font(.footnote)
            if let message = model.message ?? model.link?.error { Text(message).font(.footnote) }
          }.navigationTitle("Storage & sync")
        }
        if model.manifest.context.account == nil {
          Text("Sign in and open Apple Watch in the phone app to send music.").font(.footnote)
        }
      }.navigationTitle("Pig Music")
    }.tint(.pink)
  }
}
private struct WatchSongs: View {
  let model: WatchModel
  let ids: [String]
  let title: String
  var body: some View {
    List {
      Button("Play all") { Task { await model.play(ids) } }.disabled(ids.isEmpty)
      Button("Shuffle") { Task { await model.play(ids.shuffled()) } }.disabled(ids.isEmpty)
      ForEach(Array(ids.enumerated()), id: \.offset) { _, id in
        if let song = model.manifest.songs.first(where: { $0.id == id }) {
          NavigationLink {
            List {
              Button("Play", systemImage: "play.fill") { Task { await model.play([id]) } }.disabled(
                model.receipt?.ready[id] == nil)
              Button("Remove download", role: .destructive) {
                Task { await model.send("remove", songIds: [id]) }
              }
              if model.receipt?.ready[id] == nil { Text("Waiting for transfer") }
            }.navigationTitle(song.track.title)
          } label: {
            VStack(alignment: .leading) {
              Text(song.track.title)
              Text(song.track.artist).font(.caption)
            }
          }
        }
      }
    }.navigationTitle(title)
  }
}
private struct WatchNowPlaying: View {
  @Bindable var model: WatchModel
  var body: some View {
    List {
      if model.queue.indices.contains(model.playback.index) {
        Text(model.queue[model.playback.index].track.title).font(.headline)
        Text(model.queue[model.playback.index].track.artist).font(.caption)
      }
      HStack {
        Button {
          model.previous()
        } label: {
          Image(systemName: "backward.end.fill")
        }.accessibilityLabel("Previous song")
        Button {
          model.toggle()
        } label: {
          Image(systemName: model.playback.wantsPlayback ? "pause.fill" : "play.fill")
        }.accessibilityLabel(model.playback.wantsPlayback ? "Pause" : "Play")
        Button {
          model.next()
        } label: {
          Image(systemName: "forward.end.fill")
        }.accessibilityLabel("Next song")
      }.buttonStyle(.plain)
      Text("\(Int(model.playback.elapsed)) / \(Int(model.playback.duration)) seconds").font(
        .caption)
      Slider(
        value: Binding(
          get: { min(model.playback.duration, model.playback.elapsed) }, set: { model.seek($0) }),
        in: 0...max(1, model.playback.duration)
      ).accessibilityLabel("Playback position")
      Slider(value: $model.volume, in: 0...1).accessibilityLabel("Volume")
      if let error = model.playback.error ?? model.message {
        Text(error).font(.footnote)
        Button("Retry playback") { Task { await model.retry() } }
      }
    }.navigationTitle("Now playing")
  }
}
private struct WatchPhoneLibrary: View {
  @Bindable var model: WatchModel
  @State private var query = ""
  var body: some View {
    List {
      TextField("Search phone library", text: $query).onSubmit {
        Task { await model.search(query) }
      }
      Button("Search") { Task { await model.search(query) } }.disabled(model.loading)
      if model.loading { ProgressView() }
      ForEach(model.searchResults) { track in
        Button {
          Task { await model.send("download", songIds: [track.id]) }
        } label: {
          VStack(alignment: .leading) {
            Text(track.title)
            Text(track.artist).font(.caption)
            Label("Download to Watch", systemImage: "arrow.down.circle").font(.caption)
          }
        }
      }
      if !model.searchResults.isEmpty, model.searchResults.count % 50 == 0 {
        Button("More songs") {
          Task { await model.search(query, offset: model.searchResults.count) }
        }
      }
      if let message = model.message { Text(message).font(.footnote) }
    }.navigationTitle("Phone library").task { await model.search("") }
  }
}
