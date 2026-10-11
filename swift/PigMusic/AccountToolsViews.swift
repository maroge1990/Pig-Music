import PigBrand
import PigDomain
import SwiftUI

struct PreferencesView: View {
  let model: AppModel
  @State private var preferences = AccountPreferences()
  @State private var loading = false
  @State private var message: String?
  var body: some View {
    Form {
      Picker("Appearance", selection: $preferences.appearance) {
        Text("System").tag("system")
        Text("Light").tag("light")
        Text("Dark").tag("dark")
      }
      Button("Save preferences") { Task { await save() } }.disabled(loading || !model.canMutate)
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Appearance").task {
      preferences = model.preferences
    }
  }
  private func save() async {
    loading = true
    defer { loading = false }
    let value = preferences
    do {
      let confirmed = try await model.saveEdit(
        OfflineMutation(action: "preferences", preferences: value))
      model.preferences = value
      await model.cachePreferences()
      message =
        confirmed ? "Preferences saved." : "Preferences saved on this phone; waiting to sync."
    } catch { message = error.localizedDescription }
  }
}
struct PasswordView: View {
  let model: AppModel
  @State private var current = ""
  @State private var password = ""
  @State private var repeatPassword = ""
  @State private var loading = false
  @State private var message: String?
  var body: some View {
    Form {
      SecureField("Current password", text: $current).textContentType(.password)
      SecureField("New password", text: $password).textContentType(.newPassword)
      SecureField("Repeat new password", text: $repeatPassword).textContentType(.newPassword)
      Text("Use at least 12 characters. Other sessions are revoked when the password changes.")
        .font(PigType.footnote)
      Button("Change password") {
        Task {
          loading = true
          defer {
            loading = false
            current = ""
            password = ""
            repeatPassword = ""
          }
          let old = current
          let new = password
          do {
            try await model.performPersonal {
              try await $0.changePassword(current: old, password: new)
            }
            message = "Password changed."
          } catch { message = error.localizedDescription }
        }
      }.disabled(
        loading || !model.canMutate || current.isEmpty || password.count < 12
          || password != repeatPassword)
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Password")
  }
}
struct SessionsView: View {
  let model: AppModel
  @State private var sessions: [AccountSession] = []
  @State private var loading = false
  @State private var message: String?
  @State private var revoking: AccountSession?
  var body: some View {
    List {
      ForEach(sessions) { session in
        VStack(alignment: .leading) {
          Text(session.deviceName.isEmpty ? session.kind : session.deviceName)
          Text("Last seen \(Date(timeIntervalSince1970:session.lastSeenAt).formatted())").font(
            PigType.caption)
          if session.revokedAt != nil {
            Text("Revoked").foregroundStyle(.secondary)
          } else {
            Button("Revoke session", role: .destructive) { revoking = session }.disabled(
              loading || !model.canMutate)
          }
        }
      }
      if let message { Text(message).font(PigType.footnote) }
      if loading { ProgressView() }
    }.navigationTitle("Devices and sessions").task { await load() }
      .toolbar {
        Button("Refresh", systemImage: "arrow.clockwise") { Task { await load() } }.disabled(
          loading)
      }
      .confirmationDialog(
        "Revoke this session? Revoking this device signs it out.",
        isPresented: Binding(get: { revoking != nil }, set: { if !$0 { revoking = nil } })
      ) {
        if let session = revoking {
          Button("Revoke", role: .destructive) {
            Task {
              loading = true
              do {
                try await model.performPersonal { try await $0.revokeSession(id: session.id) }
              } catch { message = error.localizedDescription }
              revoking = nil
              loading = false
              await load()
            }
          }
        }
      }
  }
  private func load() async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    do { sessions = try await model.readCatalogue { try await $0.sessions() } } catch {
      message = error.localizedDescription
    }
  }
}
struct PlexView: View {
  let model: AppModel
  @State private var token = ""
  @State private var label = "My Plex account"
  @State private var configured = false
  @State private var loading = false
  @State private var message: String?
  var body: some View {
    Form {
      Text(configured ? "Personal Plex account configured" : "No personal Plex account configured")
      TextField("Account label", text: $label)
      SecureField("Plex token", text: $token).textInputAutocapitalization(.never)
        .autocorrectionDisabled()
      Text(
        "This token maps your playlists to your Plex account. Global Plex server configuration stays in web Admin."
      ).font(PigType.footnote)
      Button("Save mapping") {
        Task {
          loading = true
          defer {
            loading = false
            token = ""
          }
          let secret = token
          let name = label
          do {
            let result = try await model.performPersonal {
              try await $0.savePlex(token: secret, label: name)
            }
            configured = result.configured
            message = "Mapping saved."
          } catch { message = error.localizedDescription }
        }
      }.disabled(loading || !model.canMutate || token.isEmpty)
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Personal Plex").task {
      do {
        let value = try await model.readCatalogue { try await $0.plex() }
        configured = value.configured
        label = value.label ?? label
      } catch { message = error.localizedDescription }
    }
  }
}
struct QualityView: View {
  let model: AppModel
  var scope = "system"
  var id = "*"
  @State private var quality: QualitySettings?
  @State private var selected = "inherit"
  @State private var loading = false
  @State private var message: String?
  var body: some View {
    Form {
      if let quality {
        Text("Household default: \(quality.householdDefault)").font(PigType.footnote)
        Picker("My preference", selection: $selected) {
          Text("Inherit default").tag("inherit")
          ForEach(quality.options) { option in Text(option.label).tag(option.value) }
        }
        Text(
          "Shared files keep the highest requested quality. This preference affects server acquisition, not the size of downloads to this device."
        ).font(PigType.footnote)
        Button("Save preference") {
          Task {
            loading = true
            defer { loading = false }
            let value = selected == "inherit" ? nil : selected
            do {
              try await model.performPersonal {
                try await $0.saveQuality(scope: scope, id: id, preferred: value)
              }
              message = "Preference saved."
            } catch { message = error.localizedDescription }
          }
        }.disabled(loading || !model.canMutate)
      } else {
        ProgressView()
      }
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Server quality").task {
      do {
        let value = try await model.readCatalogue { try await $0.quality() }
        quality = value
        selected =
          value.preferences.first(where: { $0.scope == scope && $0.itemId == id })?.preferred
          ?? "inherit"
      } catch { message = error.localizedDescription }
    }
  }
}
struct RemovalView: View {
  let model: AppModel
  let tracks: [Track]
  @State private var preview: RemovalPreview?
  @State private var result: RemovalResult?
  @State private var loading = false
  @State private var message: String?
  @State private var confirming = false
  var body: some View {
    Form {
      if let result {
        Text("Removed \(result.removed) songs from your library.")
        Button("Undo removal") { Task { await undo(result) } }.disabled(
          loading || !model.canMutate || Date().timeIntervalSince1970 > result.undoUntil)
        Text(
          "Undo is available briefly. After it expires, ask the administrator to check Recovery."
        ).font(PigType.footnote)
      } else if let preview {
        Text(
          "\(preview.deleteCount) files have no other holders and will move to Recovery. \(preview.keepCount) remain for other people."
        )
        ForEach(preview.items) { item in
          Text(
            item.deleteFile
              ? "Move file to Recovery" : "Keep file for \(item.keptFor.joined(separator:", "))"
          ).font(PigType.footnote)
        }
        Button("Remove from my library", role: .destructive) { confirming = true }.disabled(
          loading || !model.canMutate)
      } else {
        Button("Preview removal") { Task { await load() } }.disabled(
          loading || !model.canMutate || tracks.count > 500)
      }
      if loading { ProgressView() }
      if let message { Text(message).font(PigType.footnote) }
    }.navigationTitle("Remove music").task { await load() }
      .confirmationDialog(
        "Confirm removal and the file effects shown above?", isPresented: $confirming
      ) { Button("Remove music", role: .destructive) { Task { await remove() } } }
  }
  private func load() async {
    guard !loading else { return }
    loading = true
    defer { loading = false }
    let ids = tracks.map(\.id)
    do { preview = try await model.readCatalogue { try await $0.removalPreview(ids: ids) } } catch {
      message = error.localizedDescription
    }
  }
  private func remove() async {
    guard let preview, !loading else { return }
    loading = true
    defer { loading = false }
    let ids = tracks.map(\.id)
    let token = preview.confirmation
    do {
      result = try await model.performPersonal {
        try await $0.removeMusic(ids: ids, confirmation: token)
      }
    } catch {
      self.preview = nil
      message = error.localizedDescription + " Preview again before confirming."
    }
  }
  private func undo(_ result: RemovalResult) async {
    loading = true
    defer { loading = false }
    do {
      try await model.performPersonal { try await $0.undoRemoval(id: result.id) }
      self.result = nil
      preview = nil
      message = "Music restored."
    } catch { message = error.localizedDescription }
  }
}
