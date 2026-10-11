import PigBrand
import PigDomain
import SwiftUI
import UniformTypeIdentifiers

struct PlaylistToolsView: View {
  let model: AppModel
  @State private var name = ""
  @State private var selecting = false
  @State private var imported: Data?
  @State private var preview: ImportPreview?
  @State private var message: String?
  @State private var loading = false
  var body: some View {
    Form {
      Section("New playlist") {
        TextField("Playlist name", text: $name)
        Button("Create playlist") { Task { await create() } }.disabled(
          name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || loading
            || !model.canMutate)
      }
      Section("Apple Music XML") {
        Text("Import personal playlists and matching metadata. This does not download songs.").font(
          PigType.footnote)
        Button("Choose XML export") { selecting = true }.disabled(loading)
        if let imported {
          Text(
            "Selected \(ByteCountFormatter.string(fromByteCount:Int64(imported.count),countStyle:.file)) export"
          )
          Button("Review matches") { Task { await review(imported) } }.disabled(loading)
          if let preview {
            Text(
              "\(preview.playlists) playlists · \(preview.tracks) songs. \(preview.saved) in your library, \(preview.household) in the household, \(preview.missing) missing."
            ).font(PigType.footnote)
          }
          Button("Import playlists") { Task { await submit(imported) } }.disabled(
            loading || !model.canMutate)
        }
      }
      if loading { ProgressView() }
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Playlist tools")
      .fileImporter(isPresented: $selecting, allowedContentTypes: [.xml]) { result in
        do {
          let url = try result.get()
          let access = url.startAccessingSecurityScopedResource()
          defer { if access { url.stopAccessingSecurityScopedResource() } }
          let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
          guard size > 0 && size <= 20 * 1024 * 1024 else { throw CocoaError(.fileReadTooLarge) }
          imported = try Data(contentsOf: url)
          preview = nil
          message =
            "Review the selected export before importing. Existing imported playlists are updated; unrelated playlists are retained."
        } catch { message = error.localizedDescription }
      }
  }
  private func create() async {
    loading = true
    defer { loading = false }
    let value = name.trimmingCharacters(in: .whitespacesAndNewlines)
    do {
      _ = try await model.performPersonal { try await $0.createPlaylist(name: value) }
      name = ""
      message = "Playlist created."
    } catch { message = error.localizedDescription }
  }
  private func review(_ data: Data) async {
    loading = true
    defer { loading = false }
    do {
      preview = try await model.readCatalogue { try await $0.previewImport(data) }
      message = nil
    } catch { message = error.localizedDescription }
  }
  private func submit(_ data: Data) async {
    loading = true
    defer { loading = false }
    do {
      let result = try await model.performPersonal { try await $0.importApple(data) }
      imported = nil
      message = "Imported \(result.playlists) playlists and \(result.tracks) song records."
    } catch { message = error.localizedDescription }
  }
}

struct AddToPlaylistView: View {
  let model: AppModel
  let track: Track
  @State private var message: String?
  @State private var loading = false
  var body: some View {
    List {
      ForEach(model.playlists.filter { $0.favourites != true }) { playlist in
        Button(playlist.name) {
          Task {
            loading = true
            defer { loading = false }
            do {
              _ = try await model.performPersonal {
                try await $0.addToPlaylist(id: playlist.id, track: track)
              }
              message = "Added to \(playlist.name). Repeated songs are kept as separate entries."
            } catch { message = error.localizedDescription }
          }
        }.disabled(loading || !model.canMutate)
      }
      NavigationLink("Create or import playlists") { PlaylistToolsView(model: model) }
      if loading { ProgressView() }
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Add to playlist")
  }
}

struct PlaylistView: View {
  @Bindable var model: AppModel
  @State private var playlist: Playlist
  @State private var name: String
  @State private var message: String?
  @State private var loading = false
  @State private var deleting = false
  @Environment(\.dismiss) private var dismiss
  init(model: AppModel, playlist: Playlist) {
    self.model = model
    _playlist = State(initialValue: playlist)
    _name = State(initialValue: playlist.name)
  }
  private var songs: [Track] { (playlist.entries ?? []).map(\.playbackTrack) }
  var body: some View {
    List {
      Section {
        Button("Play playlist", systemImage: "play.fill") { model.play(songs) }.disabled(
          songs.isEmpty)
        Button("Shuffle playlist", systemImage: "shuffle") { model.play(songs.shuffled()) }
          .disabled(songs.isEmpty)
        Button("Download originals", systemImage: "arrow.down.circle") {
          Task { await model.download(songs) }
        }.disabled(songs.isEmpty)
        Button("Download AAC copies") { Task { await model.download(songs, quality: "aac") } }
          .disabled(songs.isEmpty)
        if playlist.favourites != true {
          TextField("Name", text: $name)
          Button("Save name") { Task { await edit(name: name) } }.disabled(
            loading || !model.canMutate || name.isEmpty || name == playlist.name)
        }
      }
      if let message { Text(message).font(PigType.footnote) }
      ForEach(Array((playlist.entries ?? []).enumerated()), id: \.element.entryId) { index, entry in
        SongButton(model: model, track: entry.playbackTrack) { model.play(songs, at: index) }
          .swipeActions {
            Button("Remove", role: .destructive) { Task { await remove(index) } }.disabled(
              loading || !model.canMutate)
          }
      }
      .onMove { from, to in
        var order = Array((playlist.entries ?? []).indices)
        order.move(fromOffsets: from, toOffset: to)
        Task { await edit(order: order) }
      }
      .moveDisabled(loading || !model.canMutate)
      if playlist.favourites != true {
        Button("Delete playlist", role: .destructive) { deleting = true }.disabled(
          loading || !model.canMutate)
      }
    }.navigationTitle(playlist.name)
      .toolbar {
        EditButton()
        Button("Refresh", systemImage: "arrow.clockwise") { Task { await load() } }.disabled(
          loading)
      }
      .task { await load() }
      .confirmationDialog("Delete \(playlist.name)?", isPresented: $deleting) {
        Button("Delete playlist", role: .destructive) { Task { await delete() } }
      }
  }
  private func load() async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    let id = playlist.id
    do {
      playlist = try await model.readCatalogue { try await $0.playlist(id: id) }
      name = playlist.name
      message = nil
    } catch is CancellationError {} catch { message = error.localizedDescription }
  }
  private func edit(name: String? = nil, order: [Int]? = nil) async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    let id = playlist.id
    let revision = playlist.revision
    do {
      playlist = try await model.performPersonal {
        try await $0.editPlaylist(id: id, revision: revision, name: name, order: order)
      }
      self.name = playlist.name
      message = nil
    } catch { message = error.localizedDescription + " Refresh before reapplying your edit." }
  }
  private func remove(_ index: Int) async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    let id = playlist.id
    let revision = playlist.revision
    do {
      playlist = try await model.performPersonal {
        try await $0.removePlaylistEntry(id: id, revision: revision, position: index)
      }
      message = nil
    } catch { message = error.localizedDescription + " Refresh before reapplying your edit." }
  }
  private func delete() async {
    loading = true
    defer { loading = false }
    let id = playlist.id
    let revision = playlist.revision
    do {
      try await model.performPersonal { try await $0.deletePlaylist(id: id, revision: revision) }
      dismiss()
    } catch { message = error.localizedDescription }
  }
}
