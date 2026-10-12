import PigBrand
import PigCompanion
import PigDomain
import PigPlayback
import SwiftUI

@main struct PigMusicWatchApp: App {
  @State private var model = WatchModel()
  @State private var starting = true
  @Environment(\.scenePhase) private var scenePhase
  var body: some Scene {
    WindowGroup {
      WatchLibraryView(model: model)
        .overlay { if starting { PigBrandSplash(size: 120) } }
        .task {
          await model.reload()
          starting = false
        }
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
        Image("PigLockup").resizable().scaledToFit().frame(height: 40)
          .frame(maxWidth: .infinity).accessibilityHidden(true).listRowBackground(Color.clear)
        WatchNowPlayingRow(model: model)
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
                  Text(album.artist).font(.caption).foregroundStyle(.secondary)
                }
              }
            }
          }.pigBrandedCanvas().navigationTitle("Albums")
        }
        ForEach(model.manifest.collections.filter { !$0.songIds.isEmpty }) { collection in
          NavigationLink(collection.favourites ? "Favourites" : collection.name) {
            WatchSongs(model: model, ids: collection.songIds, title: collection.name)
          }
        }
        NavigationLink("Phone remote") {
          List {
            Button("Previous", systemImage: "backward.end.fill") {
              Task { await model.send("previous") }
            }
            Button("Play / pause", systemImage: "playpause.fill") {
              Task { await model.send("playPause") }
            }
            Button("Next", systemImage: "forward.end.fill") { Task { await model.send("next") } }
          }.pigBrandedCanvas().navigationTitle("Phone remote")
        }
        NavigationLink("Storage & sync") {
          List {
            Text("\(model.receipt?.ready.count ?? 0) songs downloaded").fontDesign(.rounded)
              .monospacedDigit()
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
          }.pigBrandedCanvas().navigationTitle("Storage & sync")
        }
        if model.manifest.context.account == nil {
          Text("Sign in and open Apple Watch in the phone app to send music.").font(.footnote)
        }
      }.pigBrandedCanvas().navigationTitle("Pig Music")
    }.pigBrandedCanvas()
  }
}
private struct WatchNowPlayingRow: View {
  @Bindable var model: WatchModel
  var body: some View {
    if model.queue.indices.contains(model.playback.index) {
      NavigationLink {
        WatchNowPlaying(model: model)
      } label: {
        Label {
          VStack(alignment: .leading) {
            Text("Now playing").font(.caption).foregroundStyle(.secondary)
            Text(model.queue[model.playback.index].track.title).lineLimit(1)
          }
        } icon: {
          Image(systemName: model.playback.state == .playing ? "waveform" : "pause.fill")
        }
      }
    }
  }
}
private struct WatchSongs: View {
  let model: WatchModel
  let ids: [String]
  let title: String
  var body: some View {
    List {
      HStack {
        Button {
          Task { await model.play(ids) }
        } label: {
          Label("Play", systemImage: "play.fill")
        }.pigPrimaryAction()
        Button {
          Task { await model.play(ids.shuffled()) }
        } label: {
          Image(systemName: "shuffle")
        }.accessibilityLabel("Shuffle")
      }.disabled(ids.isEmpty).listRowBackground(Color.clear)
      // One tap plays from this song; swipe to remove its download.
      ForEach(Array(ids.enumerated()), id: \.offset) { index, id in
        if let song = model.manifest.songs.first(where: { $0.id == id }) {
          let ready = model.receipt?.ready[id] != nil
          Button {
            Task { await model.play(ids, at: index) }
          } label: {
            VStack(alignment: .leading) {
              Text(song.track.title).lineLimit(2)
              Text(ready ? song.track.artist : "Waiting for transfer").font(.caption)
                .foregroundStyle(.secondary).lineLimit(1)
            }
          }
          .disabled(!ready)
          .swipeActions {
            Button("Remove", role: .destructive) {
              Task { await model.send("remove", songIds: [id]) }
            }
          }
        }
      }
    }.pigBrandedCanvas().navigationTitle(title)
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
          Image(systemName: "backward.end.fill").frame(minWidth: 40, minHeight: 44)
        }.accessibilityLabel("Previous song")
        Button {
          model.toggle()
        } label: {
          Image(systemName: model.playback.wantsPlayback ? "pause.fill" : "play.fill")
            .frame(minWidth: 40, minHeight: 44)
        }.pigPrimaryAction().accessibilityLabel(model.playback.wantsPlayback ? "Pause" : "Play")
        Button {
          model.next()
        } label: {
          Image(systemName: "forward.end.fill").frame(minWidth: 40, minHeight: 44)
        }.accessibilityLabel("Next song")
      }.buttonStyle(.plain).padding(8).pigFloatingControls().listRowBackground(Color.clear)
      Text("\(clock(model.playback.elapsed)) / \(clock(model.playback.duration))").font(.caption)
        .fontDesign(.rounded).monospacedDigit()
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
    }.pigBrandedCanvas().navigationTitle("Now playing")
  }
  private func clock(_ seconds: Double) -> String {
    guard seconds.isFinite, seconds > 0 else { return "0:00" }
    let value = Int(seconds)
    return String(format: "%d:%02d", value / 60, value % 60)
  }
}
