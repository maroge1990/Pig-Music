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
  @State private var importSelection: AppleImportSelection?
  @State private var selectedPlaylists: Set<Int> = []
  @State private var includeOtherTracks = false
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
          if let importSelection {
            ForEach(importSelection.playlists) { playlist in
              Toggle(
                "\(playlist.name) · \(playlist.songs) songs",
                isOn: Binding(
                  get: { selectedPlaylists.contains(playlist.id) },
                  set: { enabled in
                    if enabled {
                      selectedPlaylists.insert(playlist.id)
                    } else {
                      selectedPlaylists.remove(playlist.id)
                    }
                    preview = nil
                  }))
            }
            Toggle("Include music outside selected playlists", isOn: $includeOtherTracks)
              .onChange(of: includeOtherTracks) { preview = nil }
          }
          Button("Review matches") { Task { await review(imported) } }.disabled(
            loading || selectedPlaylists.isEmpty)
          if let preview {
            Text(
              "\(preview.playlists) playlists · \(preview.tracks) songs. \(preview.saved) in your library, \(preview.household) in the household, \(preview.missing) missing."
            ).font(PigType.footnote)
          }
          Button("Import playlists") { Task { await submit(imported) } }.disabled(
            loading || !model.canMutate || selectedPlaylists.isEmpty || preview == nil)
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
          let data = try Data(contentsOf: url)
          let selection = try AppleImportSelection(data: data)
          imported = data
          importSelection = selection
          selectedPlaylists = Set(selection.playlists.map(\.id))
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
      let confirmed = try await model.saveEdit(OfflineMutation(action: "create", name: value))
      name = ""
      message =
        confirmed ? "Playlist created." : "New playlist saved on this phone; waiting to sync."
    } catch { message = error.localizedDescription }
  }
  private func review(_ data: Data) async {
    loading = true
    defer { loading = false }
    do {
      let selected =
        try importSelection?.export(
          selected: selectedPlaylists, includeOtherTracks: includeOtherTracks) ?? data
      preview = try await model.readCatalogue { try await $0.previewImport(selected) }
      message = nil
    } catch { message = error.localizedDescription }
  }
  private func submit(_ data: Data) async {
    loading = true
    defer { loading = false }
    do {
      let selected =
        try importSelection?.export(
          selected: selectedPlaylists, includeOtherTracks: includeOtherTracks) ?? data
      let result = try await model.performPersonal { try await $0.importApple(selected) }
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
              let confirmed = try await model.saveEdit(
                OfflineMutation(action: "append", playlistId: playlist.id, track: track))
              message =
                confirmed
                ? "Added to \(playlist.name). Repeated songs are kept as separate entries."
                : "Playlist addition saved on this phone; waiting to sync."
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
        Button("Send to Apple Watch", systemImage: "applewatch") {
          Task { await model.watch?.enqueue(songs) }
        }.disabled(songs.isEmpty)
        Button("Download originals", systemImage: "arrow.down.circle") {
          Task { await model.download(songs) }
        }.disabled(songs.isEmpty)
        Button("Download AAC copies") { Task { await model.download(songs, quality: "aac") } }
          .disabled(songs.isEmpty)
        if let plex = playlist.plex {
          Text(
            "Plex export: \(plex.status?.replacingOccurrences(of: "_", with: " ") ?? "Waiting for sync")"
          ).font(PigType.footnote)
          Text(
            "\(plex.availableCount ?? 0) available · \(plex.pendingCount ?? 0) pending · \(plex.repeatedCount ?? 0) repeats combined by Plex"
          ).font(PigType.caption)
        }
        Text(
          "Your connected Plex account syncs playlists automatically. Missing songs wait for files to be exported to Plex."
        ).font(PigType.footnote)
        if playlist.favourites != true {
          TextField("Name", text: $name)
          Button("Save name") { Task { await edit(name: name) } }.disabled(
            loading || !model.canMutate
              || model.pendingEdits.contains(where: { $0.mutation.playlistId == playlist.id })
              || name.isEmpty || name == playlist.name)
        }
      }
      if let message { Text(message).font(PigType.footnote) }
      ForEach(Array((playlist.entries ?? []).enumerated()), id: \.element.entryId) { index, entry in
        SongButton(model: model, track: entry.playbackTrack) { model.play(songs, at: index) }
          .swipeActions {
            Button("Remove", role: .destructive) { Task { await remove(index) } }.disabled(
              loading || !model.canMutate
                || model.pendingEdits.contains(where: { $0.mutation.playlistId == playlist.id }))
          }
      }
      .onMove { from, to in
        var order = Array((playlist.entries ?? []).indices)
        order.move(fromOffsets: from, toOffset: to)
        Task { await edit(order: order) }
      }
      .moveDisabled(
        loading || !model.canMutate
          || model.pendingEdits.contains(where: { $0.mutation.playlistId == playlist.id }))
      if playlist.favourites != true {
        Button("Delete playlist", role: .destructive) { deleting = true }.disabled(
          loading || !model.canMutate
            || model.pendingEdits.contains(where: { $0.mutation.playlistId == playlist.id }))
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
      playlist = try await model.cachedCatalogue(key: "playlist:" + id) {
        try await $0.playlist(id: id)
      }
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
      let confirmed = try await model.saveEdit(
        OfflineMutation(
          action: order == nil ? "rename" : "reorder", playlistId: id, name: name,
          revision: revision, order: order))
      if confirmed, let current = model.playlists.first(where: { $0.id == id }) {
        playlist = current
        self.name = current.name
      }
      message =
        confirmed
        ? nil : "Edit saved on this phone. Other playlist edits wait for this one to sync."
    } catch { message = error.localizedDescription + " Refresh before reapplying your edit." }
  }
  private func remove(_ index: Int) async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    let id = playlist.id
    let revision = playlist.revision
    do {
      let confirmed = try await model.saveEdit(
        OfflineMutation(action: "remove", playlistId: id, revision: revision, position: index))
      if confirmed, let current = model.playlists.first(where: { $0.id == id }) {
        playlist = current
      }
      message = confirmed ? nil : "Removal saved on this phone; waiting to sync."
    } catch { message = error.localizedDescription + " Refresh before reapplying your edit." }
  }
  private func delete() async {
    loading = true
    defer { loading = false }
    let id = playlist.id
    let revision = playlist.revision
    do {
      _ = try await model.saveEdit(
        OfflineMutation(action: "delete", playlistId: id, revision: revision))
      dismiss()
    } catch { message = error.localizedDescription }
  }
}
