import PigAPI
import SwiftUI
import UIKit
import VisionKit

@main
struct PigMusicSpikeApp: App {
    var body: some Scene {
        WindowGroup { ConnectivityView() }
    }
}

struct ConnectivityView: View {
    @State private var saved = SavedServer.load()

    var body: some View {
        NavigationStack {
            Group {
                if let saved {
                    SignedInView(server: saved) { self.saved = nil }
                } else {
                    WelcomeView { self.saved = $0 }
                }
            }
            .navigationTitle("Pig Music spike")
        }
    }
}

private func message(for error: Error) -> String {
    switch error as? OnboardingError {
    case .inviteExpiredOrUsed: "This invite has expired or was already used. Ask for a new one."
    case .passwordNotAccepted: "That password was not accepted. Use at least 12 characters."
    case .invalidCredentials: "Wrong username or password."
    case .rateLimited: "Too many attempts. Wait a minute and try again."
    case .insecureServer: "The server address must start with https://."
    case .unreachable: "Could not reach the server. Check the address and your connection."
    case .accountCreatedSignInFailed(let username):
        "Your account (\(username)) was created, but signing in failed. Use Add my server to sign in with that username."
    case .unexpected(let status): "The server returned an unexpected response (\(status))."
    case nil: "Something went wrong."
    }
}

// MARK: - Signed in

private struct SignedInView: View {
    let server: SavedServer
    let onForget: () -> Void
    @State private var status = ""
    @State private var busy = false

    var body: some View {
        Form {
            Section("Signed in") {
                LabeledContent("Name", value: server.displayName)
                LabeledContent("Server", value: server.host)
            }
            Section {
                Button("Check connection") { check() }.disabled(busy)
                if !status.isEmpty { Text(status) }
                Button("Sign out of this server", role: .destructive) {
                    Task {
                        do {
                            try await Onboarding().signOut(server)
                            onForget()
                        } catch {
                            status = "Could not clear the saved sign-in."
                        }
                    }
                }
            }
            Section("Device checks") {
                Text("This app tests connectivity and sign-in only. Watch installation, refresh, background transfers and offline playback need separate device evidence.")
            }
        }
    }

    private func check() {
        busy = true
        Task {
            defer { busy = false }
            do {
                let client = try PigClient.make(server: server.origin.absoluteString, vault: server.tokenVault())
                switch try await client.me_api_v1_me_get(.init()) {
                case .ok(let ok): status = "Connected as \(try ok.body.json.display_name)."
                case .unauthorized: status = "This device was signed out by the server. Sign out here and join again."
                default: status = "The server answered, but not with your account."
                }
            } catch {
                status = "Connection failed. Check the server and your network connection."
            }
        }
    }
}

// MARK: - Not signed in

private struct WelcomeView: View {
    let onSaved: (SavedServer) -> Void
    var body: some View {
        Form {
            Section {
                NavigationLink("Join with an invite") { JoinView(onSaved: onSaved) }
                NavigationLink("Add my server") { AddServerView(onSaved: onSaved) }
            } footer: {
                Text("Join with an invite if someone shared a Pig Music link or QR code with you. Add my server if you run your own.")
            }
        }
    }
}

private struct JoinView: View {
    let onSaved: (SavedServer) -> Void
    @State private var invite: Invite?
    @State private var pasted = ""
    @State private var scanning = false
    @State private var password = ""
    @State private var confirm = ""
    @State private var errorText: String?
    @State private var busy = false

    var body: some View {
        Form {
            if let invite {
                Section("Joining \(invite.server.host ?? "server")") {
                    SecureField("Choose a password (12+ characters)", text: $password).textContentType(.newPassword)
                    SecureField("Confirm password", text: $confirm).textContentType(.newPassword)
                    Button("Join") { join(invite) }.disabled(busy || password.count < 12 || password != confirm)
                    if !confirm.isEmpty && password != confirm { Text("Passwords do not match.") }
                }
                Section { Button("Use a different invite") { self.invite = nil; errorText = nil } }
            } else {
                if DataScannerViewController.isSupported && DataScannerViewController.isAvailable {
                    Section {
                        Button("Scan invite QR code") { scanning = true }
                    }
                }
                Section("Paste invite link") {
                    TextField("https://…/#/join?code=…", text: $pasted)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                    Button("Continue") { accept(pasted) }.disabled(pasted.isEmpty)
                }
            }
            if let errorText { Section { Text(errorText).foregroundStyle(.red) } }
        }
        .navigationTitle("Join")
        .fullScreenCover(isPresented: $scanning) {
            NavigationStack {
                QRScanner { accept($0) }
                    .ignoresSafeArea()
                    .navigationTitle("Scan invite")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { scanning = false } } }
            }
        }
    }

    private func accept(_ text: String) {
        do {
            invite = try Invite.parse(text)
            errorText = nil
            scanning = false
        } catch Invite.Failure.insecureServer {
            errorText = "Invite links must use https://."
        } catch Invite.Failure.invalidCode {
            errorText = "The invite code looks wrong. Ask for a new link."
        } catch {
            self.errorText = "That is not a Pig Music invite link."
        }
    }

    private func join(_ invite: Invite) {
        busy = true
        errorText = nil
        let name = UIDevice.current.name
        let secret = password
        Task {
            defer { busy = false }
            do {
                let saved = try await Onboarding().join(invite, password: secret, deviceName: name)
                try saved.save()
                onSaved(saved)
            } catch let failure as OnboardingError {
                errorText = message(for: failure)
            } catch {
                errorText = "Could not save the sign-in on this device."
            }
        }
    }
}

private struct AddServerView: View {
    let onSaved: (SavedServer) -> Void
    @State private var address = ""
    @State private var username = ""
    @State private var password = ""
    @State private var errorText: String?
    @State private var busy = false

    var body: some View {
        Form {
            Section("Your server") {
                TextField("https://…", text: $address)
                    .textContentType(.URL)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Username", text: $username)
                    .textContentType(.username)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                SecureField("Password", text: $password).textContentType(.password)
                Button("Sign in") { signIn() }.disabled(busy || address.isEmpty || username.isEmpty || password.isEmpty)
            }
            if let errorText { Section { Text(errorText).foregroundStyle(.red) } }
        }
        .navigationTitle("Add my server")
    }

    private func signIn() {
        busy = true
        errorText = nil
        let name = UIDevice.current.name
        let (host, user, secret) = (address, username, password)
        Task {
            defer { busy = false }
            do {
                let origin = try ServerAddress.canonical(host)
                let saved = try await Onboarding().signIn(server: origin, username: user, password: secret, deviceName: name)
                try saved.save()
                onSaved(saved)
            } catch let failure as OnboardingError {
                errorText = message(for: failure)
            } catch is ServerAddress.Invalid {
                errorText = message(for: OnboardingError.insecureServer)
            } catch {
                errorText = "Could not save the sign-in on this device."
            }
        }
    }
}

// MARK: - QR scanning

private struct QRScanner: UIViewControllerRepresentable {
    let onCode: (String) -> Void

    func makeCoordinator() -> Coordinator { Coordinator(onCode: onCode) }

    func makeUIViewController(context: Context) -> DataScannerViewController {
        let controller = DataScannerViewController(recognizedDataTypes: [.barcode(symbologies: [.qr])],
                                                   qualityLevel: .balanced, recognizesMultipleItems: false,
                                                   isHighlightingEnabled: true)
        controller.delegate = context.coordinator
        try? controller.startScanning()
        return controller
    }

    func updateUIViewController(_ controller: DataScannerViewController, context: Context) {}

    @MainActor
    final class Coordinator: NSObject, DataScannerViewControllerDelegate {
        let onCode: (String) -> Void
        init(onCode: @escaping (String) -> Void) { self.onCode = onCode }

        func dataScanner(_ dataScanner: DataScannerViewController, didAdd addedItems: [RecognizedItem], allItems: [RecognizedItem]) {
            for case .barcode(let barcode) in addedItems {
                if let value = barcode.payloadStringValue { onCode(value) }
            }
        }
    }
}
