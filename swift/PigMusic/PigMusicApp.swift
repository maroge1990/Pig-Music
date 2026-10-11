import PigBrand
import SwiftUI

@main struct PigMusicApp: App {
  @State private var model = AppModel()
  @Environment(\.scenePhase) private var phase
  var body: some Scene {
    WindowGroup {
      RootView(model: model)
        .task { await model.restore() }
        .onChange(of: phase) { _, value in if value == .active { Task { await model.refresh() } } }
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
    .tint(PigBrand.accent(scheme))
    .scrollContentBackground(.hidden)
    .background(PigBrand.canvas(scheme))
  }
}

struct SignInView: View {
  @Bindable var model: AppModel
  @State private var username = ""
  @State private var password = ""
  var body: some View {
    NavigationStack {
      Form {
        Section {
          Image("PigMark").resizable().scaledToFit().frame(height: 100).frame(maxWidth: .infinity)
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
          }.disabled(model.busy || username.isEmpty || password.isEmpty || model.server.isEmpty)
        }
        if let message = model.message {
          Section {
            Text(message).foregroundStyle(.red).accessibilityLabel("Sign-in status: " + message)
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
        TabView {
          ForEach(Destination.allCases) { item in
            NavigationStack { content(item) }.tabItem {
              Label(item.rawValue, systemImage: item.symbol)
            }
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
  @Environment(\.colorScheme) private var scheme
  func body(content: Content) -> some View {
    content.scrollContentBackground(.hidden)
      .background(PigBrand.canvas(scheme))
      .toolbarBackground(PigBrand.canvas(scheme), for: .navigationBar)
  }
}
extension View {
  func pigCanvas() -> some View { modifier(PigCanvas()) }
}
