import SwiftUI

@main
struct PigMusicSpikeApp: App {
    var body: some Scene {
        WindowGroup { ConnectivityView() }
    }
}

struct ConnectivityView: View {
    @State private var server = ""
    @State private var result = "Enter the private HTTPS server URL."
    @State private var checking = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Private server") {
                    TextField("https://…ts.net", text: $server)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Check connection") {
                        checking = true
                        Task {
                            defer { checking = false }
                            do {
                                _ = try await HealthProbe.check(server: server)
                                result = "Connected. Repeat on cellular and record the result."
                            } catch {
                                result = "Connection failed. Check the URL and Tailscale connection."
                            }
                        }
                    }
                    .disabled(checking)
                    Text(result)
                }
                Section("Device checks") {
                    Text("This app tests connectivity only. Watch installation, refresh, background transfers and offline playback need separate device evidence.")
                }
            }
            .navigationTitle("Pig Music spike")
        }
    }
}
