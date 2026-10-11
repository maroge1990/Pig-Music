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

/// The Downloads tab: music requested from the server (as on the web), plus
/// music stored on this iPhone and on Apple Watch.
struct DownloadsHubView: View {
  let model: AppModel
  var body: some View {
    List {
      Section {
        NavigationLink {
          RequestsView(model: model)
        } label: {
          Label {
            VStack(alignment: .leading) {
              Text("Server requests")
              Text("Music you asked the server to get").font(PigType.footnote)
                .foregroundStyle(.secondary)
            }
          } icon: {
            Image(systemName: "server.rack")
          }
        }
        NavigationLink {
          DownloadsView(model: model)
        } label: {
          Label {
            VStack(alignment: .leading) {
              Text("On this iPhone")
              Text(deviceSummary).font(PigType.footnote).foregroundStyle(.secondary)
            }
          } icon: {
            Image(systemName: "iphone")
          }
        }
        if model.watch?.supported == true {
          NavigationLink {
            WatchDownloadsView(model: model)
          } label: {
            Label {
              VStack(alignment: .leading) {
                Text("Apple Watch")
                Text(watchSummary).font(PigType.footnote).foregroundStyle(.secondary)
              }
            } icon: {
              Image(systemName: "applewatch")
            }
          }
        }
      }
    }
    .navigationTitle("Downloads")
  }
  private var deviceSummary: String {
    let records = model.downloads?.records ?? []
    let ready = records.filter { $0.state == "ready" }.count
    let waiting = records.count - ready
    return waiting > 0 ? "\(ready) ready · \(waiting) in progress" : "\(ready) songs ready offline"
  }
  private var watchSummary: String {
    guard let receipt = model.watch?.receipt else { return "Transfers wait for your Watch" }
    return "\(receipt.ready.count) songs on Watch"
  }
}
