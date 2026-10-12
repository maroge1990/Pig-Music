import PigBrand
import PigDownloads
import SwiftUI

struct DownloadsView: View {
  let model: AppModel
  var body: some View {
    Group {
      if let downloads = model.downloads {
        DownloadList(model: model, downloads: downloads)
      } else {
        ContentUnavailableView("Connect your library", systemImage: "arrow.down.circle")
      }
    }.pigCanvas().navigationTitle("On this device")
  }
}
private struct DownloadList: View {
  let model: AppModel
  @Bindable var downloads: DownloadController
  @State private var budget = 5
  @State private var clearing = false
  var body: some View {
    List {
      if downloads.records.isEmpty {
        Text("No downloads yet. Choose songs, albums or playlists to download.").foregroundStyle(
          .secondary)
      }
      ForEach(downloads.records) { record in
        VStack(alignment: .leading) {
          Text(record.track.title)
          Text(
            "\(record.track.artist) · \(record.quality == "aac" ? "AAC" : "Original") · \(record.state)"
          ).font(PigType.caption)
          if record.state == "ready" {
            Button("Play", systemImage: "play.fill") { model.play([record.track]) }
          }
          if let value = downloads.progress[record.id], record.state != "ready" {
            ProgressView(value: value)
          }
          if let error = record.error { Text(error).font(PigType.footnote) }
          if record.state == "failed" {
            Button("Retry") {
              Task { try? await downloads.enqueue([record.track], quality: record.quality) }
            }
          }
          Button(
            record.state == "ready" ? "Remove download" : "Cancel download", role: .destructive
          ) { Task { await downloads.remove(id: record.id) } }
        }
      }
      Section("Storage") {
        Text(
          "\(ByteCountFormatter.string(fromByteCount:downloads.records.filter{$0.state == "ready"}.reduce(0){$0+$1.total},countStyle:.file)) downloaded"
        )
        Picker("Download budget", selection: $budget) {
          ForEach([1, 2, 5, 10, 20, 50], id: \.self) { Text("\($0) GB").tag($0) }
        }
        .onChange(of: budget) { _, value in
          downloads.budgetBytes = Int64(value) * 1024 * 1024 * 1024
          model.saveDownloadBudget(downloads.budgetBytes)
        }
        if downloads.usesBackgroundTransfers {
          Toggle(
            "Allow cellular downloads",
            isOn: Binding(
              get: { downloads.allowsCellular },
              set: { value in Task { await downloads.setCellular(value) } }))
        }
        Text(
          (downloads.allowsCellular
            ? "Downloads can use Wi-Fi and cellular. " : "Downloads use Wi-Fi. ")
            + "Originals are the default; AAC copies use less storage. Use AAC for originals your device cannot decode. Scheduled file transfers continue in the background. Preparing new downloads and AAC copies resumes when the app opens. Access changes reconcile when you next connect."
        ).font(PigType.footnote)
        if downloads.running || downloads.records.contains(where: { $0.state == "downloading" }) {
          Button("Pause downloads") { Task { await downloads.pause() } }
        } else {
          Button("Resume queued downloads") { downloads.resume() }
        }
        Button("Remove all device downloads", role: .destructive) { clearing = true }
      }
    }.task {
      await downloads.reload()
      budget = Int(downloads.budgetBytes / (1024 * 1024 * 1024))
    }
    .confirmationDialog(
      "Remove all music downloaded to this device? Server music is retained.",
      isPresented: $clearing
    ) { Button("Remove device downloads", role: .destructive) { Task { await downloads.clear() } } }
  }
}

/// The Downloads tab: what you asked the server, this iPhone and Apple Watch
/// to download. Each row's badge counts its queued and in-progress songs; the
/// tab badge is their total.
struct DownloadsHubView: View {
  let model: AppModel
  var body: some View {
    List {
      row("Server", detail: "Music you asked the server to get", symbol: "server.rack",
        active: model.serverActiveRequests) { RequestsView(model: model) }
      row("iPhone", detail: phoneSummary, symbol: "iphone", active: model.phoneActiveDownloads) {
        DownloadsView(model: model)
      }
      if model.watch?.supported == true {
        row("Apple Watch", detail: watchSummary, symbol: "applewatch",
          active: model.watchActiveDownloads) { WatchDownloadsView(model: model) }
      }
    }
    .navigationTitle("Downloads")
    .task {
      // Server requests have no live progress feed; poll while any are active.
      await model.refreshServerRequests()
      while model.serverActiveRequests > 0, !Task.isCancelled {
        try? await Task.sleep(for: .seconds(10))
        await model.refreshServerRequests()
      }
    }
  }
  private func row<Destination: View>(
    _ title: String, detail: String, symbol: String, active: Int,
    @ViewBuilder destination: @escaping () -> Destination
  ) -> some View {
    NavigationLink(destination: destination) {
      Label {
        VStack(alignment: .leading) {
          Text(title)
          Text(detail).font(PigType.footnote).foregroundStyle(.secondary)
        }
      } icon: {
        Image(systemName: symbol)
      }
    }.badge(active)
  }
  private var phoneSummary: String {
    let ready = model.downloads?.records.count { $0.state == "ready" } ?? 0
    return "\(ready) songs ready offline"
  }
  private var watchSummary: String {
    guard let receipt = model.watch?.receipt else { return "Transfers wait for your Watch" }
    return "\(receipt.ready.count) songs on Watch"
  }
}
