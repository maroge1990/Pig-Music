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
  case search = "Search"
  case account = "Account"
  var id: String { rawValue }
  var symbol: String {
    switch self {
    case .home: "house"
    case .library: "music.note.list"
    case .search: "magnifyingglass"
    case .account: "person.crop.circle"
    }
  }
}

struct LibraryShell: View {
  @Bindable var model: AppModel
  @State private var selection: Destination? = .home
  @State private var showPlayer = false
  @Environment(\.horizontalSizeClass) private var size
  var body: some View {
    Group {
      if size == .regular {
        NavigationSplitView {
          List(Destination.allCases, selection: $selection) { item in
            Label(item.rawValue, systemImage: item.symbol).tag(item)
          }
          .navigationTitle("Pig Music").pigCanvas()
        } detail: {
          NavigationStack { content(selection ?? .home) }
        }
      } else {
        TabView(selection: $selection) {
          ForEach(Destination.allCases) { item in
            NavigationStack { content(item) }.tabItem {
              if item == .home {
                Label(
                  item.rawValue,
                  image: selection == .home ? "pig-music-glyph-fill" : "pig-music-glyph-outline")
              } else {
                Label(item.rawValue, systemImage: item.symbol)
              }
            }.tag(Optional(item))
          }
        }
      }
    }
    .safeAreaInset(edge: .bottom) {
      if model.player.queue.current != nil {
        MiniPlayer(model: model) { showPlayer = true }
      }
    }
    .sheet(isPresented: $showPlayer) { NowPlayingView(model: model) }
    .sheet(item: $model.actionTrack) { SongActionsView(model: model, track: $0) }
  }
  @ViewBuilder private func content(_ destination: Destination) -> some View {
    Group {
      switch destination {
      case .home: HomeView(model: model)
      case .library: LibraryView(model: model)
      case .search: SearchView(model: model)
      case .account: AccountView(model: model)
      }
    }.pigCanvas()
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
