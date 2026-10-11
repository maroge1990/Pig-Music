import PigBrand
import PigDownloads
import SwiftUI
import UIKit

@main struct PigMusicApp: App {
  @UIApplicationDelegateAdaptor(PigMusicAppDelegate.self) private var delegate
  @State private var model = AppModel()
  @State private var starting = true
  @Environment(\.scenePhase) private var phase
  var body: some Scene {
    WindowGroup {
      RootView(model: model)
        .overlay { if starting { PigBrandSplash() } }
        .task {
          await model.restore()
          starting = false
        }
        .onChange(of: model.person?.id) { _, person in
          if person != nil { starting = false }
        }
        .onChange(of: phase, initial: true) { _, value in
          Task { await model.sceneActive(value == .active) }
        }
    }
  }
}

struct RootView: View {
  @Bindable var model: AppModel
  @Environment(\.colorScheme) private var scheme
  var body: some View {
    Group {
      if model.person == nil { SignInView(model: model) } else { LibraryShell(model: model) }
    }
    .preferredColorScheme(
      model.preferences.appearance == "dark"
        ? .dark : (model.preferences.appearance == "light" ? .light : nil)
    )
    .tint(PigBrand.accent(scheme))
    .scrollContentBackground(.hidden)
    .background { PigCanvasBackground() }
  }
}

struct SignInView: View {
  @Bindable var model: AppModel
  @State private var username = ""
  @State private var password = ""
  @State private var invitation = ""
  var body: some View {
    NavigationStack {
      Form {
        Section {
          Image("PigLockup").resizable().scaledToFit().frame(maxWidth: 280).frame(height: 100)
            .frame(maxWidth: .infinity)
            .accessibilityHidden(true)
          Text("Your music, wherever you are.").font(PigType.headline)
        }
        Section("Your server") {
          TextField("https://your-server.ts.net:10000", text: $model.server)
            .textContentType(.URL).keyboardType(.URL).textInputAutocapitalization(.never)
            .autocorrectionDisabled()
          Text("Connect to Tailscale before signing in away from home.").font(PigType.footnote)
        }
        Section("Your account") {
          TextField("Username", text: $username).textContentType(.username)
            .textInputAutocapitalization(.never).autocorrectionDisabled()
          SecureField("Password", text: $password).textContentType(.password)
          Button {
            Task {
              await model.signIn(username: username, password: password)
              password = ""
            }
          } label: {
            HStack {
              Text("Sign in")
              Spacer()
              if model.busy { ProgressView() }
            }
          }.pigPrimaryAction().disabled(
            model.busy || username.isEmpty || password.isEmpty || model.server.isEmpty)
        }
        Section("Join with an invitation") {
          TextField("Invitation link or code", text: $invitation).textInputAutocapitalization(
            .never
          ).autocorrectionDisabled()
          Text("Use the password above for your new account; at least 12 characters.").font(
            PigType.footnote)
          Button("Activate account") {
            Task {
              await model.join(invitation: invitation, password: password)
              password = ""
              invitation = ""
            }
          }
          .disabled(model.busy || invitation.isEmpty || password.count < 12)
        }
        if let message = model.message {
          Section {
            Text(message).foregroundStyle(Color("PigDanger")).accessibilityLabel(
              "Sign-in status: " + message)
          }
        }
      }.navigationTitle("Pig Music").pigCanvas()
    }
  }
}

private enum Destination: String, CaseIterable, Identifiable {
  case home = "Home"
  case library = "Library"
  case downloads = "Downloads"
  case search = "Search"
  var id: String { rawValue }
  var symbol: String {
    switch self {
    case .home: "house"
    case .library: "square.stack"
    case .downloads: "arrow.down.circle"
    case .search: "magnifyingglass"
    }
  }
}

/// Same sections as the web app. Account opens from the avatar, as on the web,
/// and the mini player is integrated with the tab bar like Apple Music.
struct LibraryShell: View {
  @Bindable var model: AppModel
  @State private var selection: Destination = .home
  @State private var showPlayer = false
  @State private var showAccount = false
  private var playing: Bool { model.player.queue.current != nil }
  var body: some View {
    tabs
      .sheet(isPresented: $showPlayer) { NowPlayingView(model: model) }
      .sheet(isPresented: $showAccount) {
        NavigationStack {
          AccountView(model: model).pigCanvas()
            .toolbar { Button("Done") { showAccount = false } }
        }
      }
      .sheet(item: $model.actionTrack) { SongActionsView(model: model, track: $0) }
      #if DEBUG
        // Headless UI review: --tab=<name> and --demo-play.
        .task {
          let arguments = ProcessInfo.processInfo.arguments
          if let tab = arguments.first(where: { $0.hasPrefix("--tab=") })?.dropFirst(6),
            let value = Destination.allCases.first(where: { $0.rawValue.lowercased() == tab })
          {
            selection = value
          }
          if arguments.contains("--demo-play") {
            while model.songs.isEmpty { try? await Task.sleep(for: .milliseconds(200)) }
            model.play(model.songs)
            if !arguments.contains("--demo-autoplay") { model.player.pause() }
          }
        }
      #endif
  }
  @ViewBuilder private var tabs: some View {
    let view = TabView(selection: $selection) {
      Tab(Destination.home.rawValue, systemImage: Destination.home.symbol, value: .home) {
        stack(.home)
      }
      Tab(Destination.library.rawValue, systemImage: Destination.library.symbol, value: .library) {
        stack(.library)
      }
      Tab(
        Destination.downloads.rawValue, systemImage: Destination.downloads.symbol,
        value: .downloads
      ) { stack(.downloads) }
      Tab(value: Destination.search, role: .search) { stack(.search) }
    }
    .tabViewStyle(.sidebarAdaptable)
    if #available(iOS 26.1, *) {
      view.tabBarMinimizeBehavior(.onScrollDown)
        .tabViewBottomAccessory(isEnabled: playing) {
          MiniPlayer(model: model) { showPlayer = true }
        }
    } else {
      view
    }
  }
  private var accessoryAvailable: Bool {
    if #available(iOS 26.1, *) { return true }
    return false
  }
  private func stack(_ destination: Destination) -> some View {
    NavigationStack {
      Group {
        switch destination {
        case .home: HomeView(model: model)
        case .library: LibraryView(model: model)
        case .downloads: DownloadsHubView(model: model)
        case .search: SearchView(model: model)
        }
      }
      .pigCanvas()
      // Older systems: the player docks directly above the tab bar inside each
      // tab, so it never covers the tabs or the end of a list.
      .safeAreaInset(edge: .bottom, spacing: 0) {
        if !accessoryAvailable && playing {
          MiniPlayer(model: model) { showPlayer = true }
            .pigFloatingControls().padding(.horizontal, 12).padding(.bottom, 6)
        }
      }
      .toolbar {
        if destination != .search {
          ToolbarItem(placement: .topBarTrailing) { accountButton }
        }
      }
    }
  }
  private var accountButton: some View {
    Button {
      showAccount = true
    } label: {
      AccountAvatar(name: model.person?.displayName ?? model.person?.username ?? "")
    }.accessibilityLabel("Account")
  }
}

private struct AccountAvatar: View {
  let name: String
  @Environment(\.colorScheme) private var scheme
  var body: some View {
    Text(
      name.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined()
        .uppercased()
    )
    .font(.footnote.weight(.bold)).foregroundStyle(PigBrand.textAccent(scheme))
    .frame(width: 34, height: 34)
    .background(PigBrand.accent(scheme).opacity(0.16), in: Circle())
  }
}

private struct PigCanvas: ViewModifier {
  func body(content: Content) -> some View {
    content.pigBrandedCanvas()
  }
}
extension View {
  func pigCanvas() -> some View { modifier(PigCanvas()) }
}

@MainActor final class PigMusicAppDelegate: NSObject, UIApplicationDelegate {
  func application(
    _ application: UIApplication, handleEventsForBackgroundURLSession identifier: String,
    completionHandler: @escaping () -> Void
  ) {
    BackgroundTransferHub.handleEvents(identifier: identifier, completion: completionHandler)
  }
}
