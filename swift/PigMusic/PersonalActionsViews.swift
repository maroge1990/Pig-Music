import PigBrand
import PigDomain
import SwiftUI

struct SongActionsView: View {
  let model: AppModel
  let track: Track
  @Environment(\.dismiss) private var dismiss
  @State private var addedToLibrary = false
  @State private var favourite: Bool?
  @State private var loading = false
  @State private var message: String?
  var body: some View {
    NavigationStack {
      Form {
        Section {
          VStack(alignment: .leading, spacing: 2) {
            Text(track.title).lineLimit(1)
            Text(track.artist).font(PigType.footnote).foregroundStyle(.secondary).lineLimit(1)
          }
        }
        Section {
          if let favourite {
            Button(
              favourite ? "Remove from favourites" : "Add to favourites",
              systemImage: favourite ? "heart.slash" : "heart"
            ) {
              Task { await changeFavourite(!favourite) }
            }.disabled(loading || !model.canMutate)
          } else {
            Button("Load favourite status") { Task { await loadFavourite() } }.disabled(loading)
          }
          if addedToLibrary {
            Button("Play song", systemImage: "play.fill") {
              var saved = track
              saved.serverState = "in_library"
              model.play([saved])
              dismiss()
            }
          } else if track.serverState == "household_available" {
            Button("Add to my library", systemImage: "plus") {
              Task { await add() }
            }.disabled(loading || !model.canMutate)
          } else if track.serverState == "not_in_library" {
            Button("Request song", systemImage: "arrow.down.circle") {
              Task { await request() }
            }.disabled(loading || !model.canMutate)
          }
        }
        Section {
          if model.player.queue.current != nil {
            Button("Play next") { model.player.enqueue([track], next: true) }
            Button("Add to queue") { model.player.enqueue([track]) }
          }
          NavigationLink("Add to playlist") { AddToPlaylistView(model: model, track: track) }
          if track.serverState == "in_library" || track.serverState == nil {
            Button("Download original", systemImage: "arrow.down.circle") {
              Task { await model.download([track]) }
            }
            Button("Send to Apple Watch", systemImage: "applewatch") {
              Task { message = await model.watch?.enqueue([track]) }
            }
            Button("Download smaller AAC copy") {
              Task { await model.download([track], quality: "aac") }
            }
            NavigationLink("Remove music") { RemovalView(model: model, tracks: [track]) }
          }
        } footer: {
          Text(
            "Favourites do not download music. Requests are sent to your server and are separate from downloads to this device."
          )
        }
        if loading { ProgressView() }
        if let message { Section { Text(message).font(PigType.footnote) } }
      }.pigCanvas().navigationTitle("Song actions").navigationBarTitleDisplayMode(.inline)
        .toolbar { Button("Done") { dismiss() }.disabled(loading) }
        .task { await loadFavourite() }
    }.interactiveDismissDisabled(model.mutationActive)
  }
  private func loadFavourite() async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    let key = "favourite:" + track.id
    if let pending = model.pendingEdits.last(where: {
      $0.mutation.action == "favourite" && $0.mutation.track?.id == track.id
    }) {
      favourite = pending.mutation.favourite
    } else {
      favourite = (try? await model.store?.cached(key, as: Bool.self)) ?? false
      if let confirmed = try? await model.readCatalogue({ try await $0.favourite(track) }) {
        favourite = confirmed
        try? await model.store?.cache(confirmed, key: key)
      }
    }
  }
  private func changeFavourite(_ value: Bool) async {
    guard !loading else { return }
    loading = true
    message = nil
    defer { loading = false }
    do {
      let confirmed = try await model.saveEdit(
        OfflineMutation(action: "favourite", track: track, favourite: value))
      favourite = value
      try? await model.store?.cache(value, key: "favourite:" + track.id)
      message =
        confirmed
        ? (value ? "Added to favourites." : "Removed from favourites.")
        : "Favourite edit saved on this phone; waiting to sync."
    } catch is CancellationError {} catch { message = error.localizedDescription }
  }
  private func add() async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    do {
      let count = try await model.performPersonal {
        try await $0.addMembership(trackIds: [track.id])
      }
      message = count > 0 ? "Added to your library." : "Already in your library."
      addedToLibrary = true
    } catch is CancellationError {} catch { message = error.localizedDescription }
  }
  private func request() async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    do {
      let result = try await model.performPersonal { try await $0.requestMusic([track]) }
      message =
        "Server confirmed: \(result.created) new, \(result.existing) existing, \(result.skipped) skipped."
      if !result.downloadsEnabled {
        message! += " Server downloads are disabled; requests will wait."
      }
    } catch is CancellationError {} catch { message = error.localizedDescription }
  }
}

struct RequestsView: View {
  let model: AppModel
  @State private var items: [AcquisitionRequest] = []
  @State private var next: Int?
  @State private var loading = false
  @State private var loaded = false
  @State private var enabled = true
  @State private var error: String?
  var body: some View {
    List {
      if !enabled {
        Text("Server downloads are disabled. Requests can wait until downloads are enabled.").font(
          PigType.footnote)
      }
      if loading { ProgressView("Loading requests…") }
      if let error { Text(error).font(PigType.footnote) }
      if loaded && items.isEmpty { Text("No music requests").foregroundStyle(.secondary) }
      ForEach(items) { item in
        VStack(alignment: .leading, spacing: 4) {
          Text(item.title)
          Text(item.artist).font(PigType.subhead).foregroundStyle(.secondary)
          if ["failed", "cancelled"].contains(item.status) {
            Button("Retry request") {
              Task {
                do {
                  _ = try await model.performPersonal { try await $0.retryRequest(id: item.id) }
                  await load(reset: true)
                } catch { self.error = error.localizedDescription }
              }
            }.disabled(loading || !model.canMutate)
          }
          if ["waiting_for_sources", "searching", "downloading", "validating"].contains(item.status)
          {
            Button("Cancel my request", role: .destructive) {
              Task {
                do {
                  let result = try await model.performPersonal {
                    try await $0.cancelRequest(id: item.id)
                  }
                  await load(reset: true)
                  if result.continuesForOthers {
                    self.error =
                      "Your request was cancelled. The shared download continues for another person."
                  }
                } catch { self.error = error.localizedDescription }
              }
            }.disabled(loading || !model.canMutate)
          }
          Text(item.status.replacingOccurrences(of: "_", with: " ")).font(PigType.caption)
          if let progress = item.requestProgress {
            ProgressView(value: min(1, max(0, progress)))
          }
          if let error = item.error, !error.isEmpty {
            Text(error).font(PigType.caption).foregroundStyle(.secondary)
          }
        }
      }
      if next != nil {
        Button("Load more requests") { Task { await load(reset: false) } }.disabled(loading)
      }
    }.pigCanvas().navigationTitle("Music requests")
      .toolbar {
        Button("Refresh", systemImage: "arrow.clockwise") { Task { await load(reset: true) } }
          .disabled(loading)
        Button("Clear finished") { Task { await clear() } }.disabled(loading || !model.canMutate)
      }
      .task { await load(reset: true) }
  }
  private func load(reset: Bool) async {
    guard !loading else { return }
    loading = true
    error = nil
    defer { loading = false }
    let offset = reset ? 0 : (next ?? 0)
    do {
      let page = try await model.readCatalogue { try await $0.requests(offset: offset) }
      if reset {
        items = page.items
      } else {
        for item in page.items {
          if let index = items.firstIndex(where: { $0.id == item.id }) {
            items[index] = item
          } else {
            items.append(item)
          }
        }
      }
      next = page.nextOffset
      enabled = page.downloadsEnabled
      model.serverActiveRequests = page.active
      loaded = true
    } catch is CancellationError {} catch { self.error = error.localizedDescription }
  }
  private func clear() async {
    guard !loading else { return }
    loading = true
    do {
      _ = try await model.performPersonal { try await $0.clearFinishedRequests() }
    } catch is CancellationError {
      loading = false
      return
    } catch {
      self.error = error.localizedDescription
      loading = false
      return
    }
    loading = false
    await load(reset: true)
  }
}
