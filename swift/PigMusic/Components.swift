import PigBrand
import PigDomain
import SwiftUI

/// Album or artist artwork, matching the web client: a rose halo with initials
/// while loading or when no image exists. A refresh never blanks a loaded image.
struct Artwork: View {
  let model: AppModel
  let source: AppModel.ArtworkSource?
  let title: String
  var width = 256
  var circle = false
  @Environment(\.colorScheme) private var scheme
  @State private var image: UIImage?
  @State private var loaded: AppModel.ArtworkSource?
  private var identity: String {
    "\(model.artworkNamespace)|\(model.artworkRefresh)|\(String(describing: source))|\(width)"
  }
  var body: some View {
    Color.clear.aspectRatio(1, contentMode: .fit)
      .overlay {
        if let image {
          Image(uiImage: image).resizable().scaledToFill()
        } else {
          placeholder
        }
      }
      .clipShape(RoundedRectangle(cornerRadius: circle ? 9999 : 10, style: .continuous))
      .accessibilityHidden(true)
      .task(id: identity) {
        // Another item (cell reuse): forget the old picture first.
        if loaded != source { image = nil }
        guard let next = await model.artwork(source, width: width), !Task.isCancelled else {
          return
        }
        image = next
        loaded = source
      }
  }
  private var placeholder: some View {
    ZStack {
      PigBrand.raised(scheme)
      RadialGradient(
        colors: [PigBrand.accent(scheme).opacity(0.22), .clear], center: .center, startRadius: 0,
        endRadius: 90)
      Text(initials).font(.system(.title2, design: .rounded).weight(.semibold))
        .foregroundStyle(PigBrand.accent(scheme).opacity(0.55))
        .minimumScaleFactor(0.4).padding(6)
    }
  }
  private var initials: String {
    title.split(separator: " ").prefix(2).compactMap(\.first).map(String.init).joined()
      .uppercased()
  }
}

/// Small rounded artwork used in rows, the mini player and Now Playing.
struct ArtworkThumb: View {
  let model: AppModel
  let source: AppModel.ArtworkSource?
  let title: String
  var size: CGFloat = 44
  var width = 128
  var body: some View {
    Artwork(model: model, source: source, title: title, width: width).frame(
      width: size, height: size)
  }
}

extension Track {
  var artworkSource: AppModel.ArtworkSource? {
    if let coverSha { return .stored(coverSha) }
    if let musicbrainzReleaseId, UUID(uuidString: musicbrainzReleaseId) != nil {
      return .release(musicbrainzReleaseId)
    }
    return nil
  }
  var durationText: String? {
    guard let duration, duration.isFinite, duration > 0 else { return nil }
    let seconds = Int(duration.rounded())
    return String(format: "%d:%02d", seconds / 60, seconds % 60)
  }
}

extension Album {
  var artworkSource: AppModel.ArtworkSource? { coverSha.map { .stored($0) } }
  var subtitle: String {
    [artist, year?.text, trackCount.map { "\($0) song\($0 == 1 ? "" : "s")" }]
      .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
  }
}

/// Grid card: square artwork (circle for artists) with a title and caption.
struct CollectionCard: View {
  let model: AppModel
  let source: AppModel.ArtworkSource?
  let title: String
  var caption: String?
  var circle = false
  var body: some View {
    VStack(alignment: circle ? .center : .leading, spacing: 6) {
      Artwork(model: model, source: source, title: title, width: 512, circle: circle)
      VStack(alignment: circle ? .center : .leading, spacing: 2) {
        Text(title).font(.subheadline.weight(.semibold)).lineLimit(2)
          .multilineTextAlignment(circle ? .center : .leading)
        if let caption, !caption.isEmpty {
          Text(caption).font(PigType.caption).foregroundStyle(.secondary).lineLimit(1)
        }
      }
    }
    .contentShape(Rectangle())
    .accessibilityElement(children: .combine)
  }
}

/// Saved artist card: the artwork comes from the artist's own album covers.
struct SavedArtistCard: View {
  let model: AppModel
  let artist: Artist
  @State private var sha: String?
  var body: some View {
    CollectionCard(
      model: model, source: sha.map { .stored($0) }, title: artist.name,
      caption: artist.albumCount.map { "\($0) album\($0 == 1 ? "" : "s")" }, circle: true
    )
    .task(id: "\(artist.id)|\(model.artworkRefresh)") { sha = await model.artistCover(artist) }
  }
}

let cardColumns = [GridItem(.adaptive(minimum: 150, maximum: 220), spacing: 16)]

/// Horizontally scrolling row of cards with a heading, as on the web Home.
struct Shelf<Content: View>: View {
  let title: String
  var caption: String?
  @ViewBuilder let content: Content
  var body: some View {
    VStack(alignment: .leading, spacing: 10) {
      VStack(alignment: .leading, spacing: 2) {
        Text(title).font(.title3.weight(.bold))
        if let caption { Text(caption).font(PigType.footnote).foregroundStyle(.secondary) }
      }.padding(.horizontal)
      ScrollView(.horizontal, showsIndicators: false) {
        LazyHStack(alignment: .top, spacing: 14) { content }.padding(.horizontal)
          .scrollTargetLayout()
      }.scrollTargetBehavior(.viewAligned)
    }
  }
}

/// Compact header for album, artist and playlist pages.
struct DetailHeader: View {
  let model: AppModel
  let source: AppModel.ArtworkSource?
  let eyebrow: String
  let title: String
  var subtitle: String?
  var circle = false
  @Environment(\.colorScheme) private var scheme
  var body: some View {
    HStack(alignment: .center, spacing: 16) {
      Artwork(model: model, source: source, title: title, width: 512, circle: circle)
        .frame(width: 112, height: 112)
        .shadow(color: .black.opacity(0.12), radius: 8, y: 4)
      VStack(alignment: .leading, spacing: 4) {
        Text(eyebrow).font(.caption.weight(.bold)).tracking(1.2)
          .foregroundStyle(PigBrand.textAccent(scheme))
        Text(title).font(.title2.weight(.bold)).lineLimit(3)
        if let subtitle, !subtitle.isEmpty {
          Text(subtitle).font(PigType.subhead).foregroundStyle(.secondary).lineLimit(2)
        }
      }
      Spacer(minLength: 0)
    }
    .accessibilityElement(children: .combine)
    .accessibilityAddTraits(.isHeader)
  }
}

/// The one compact action row: a Play capsule followed by round icon buttons.
struct PlayCapsule: View {
  let action: () -> Void
  var body: some View {
    Button(action: action) {
      Label("Play", systemImage: "play.fill").font(.subheadline.weight(.semibold))
        .padding(.horizontal, 10)
    }
    .pigPrimaryAction().controlSize(.regular).buttonBorderShape(.capsule)
  }
}

struct RoundIcon: View {
  let label: String
  let systemImage: String
  let action: () -> Void
  var body: some View {
    Button(action: action) { RoundIconLabel(systemImage: systemImage) }
      .buttonStyle(.plain).accessibilityLabel(label)
  }
}

struct RoundIconLabel: View {
  let systemImage: String
  @Environment(\.colorScheme) private var scheme
  @Environment(\.isEnabled) private var enabled
  var body: some View {
    Image(systemName: systemImage).font(.system(size: 16, weight: .semibold))
      .frame(width: 40, height: 40)
      .foregroundStyle(enabled ? PigBrand.text(scheme) : PigBrand.secondary(scheme))
      .background(PigBrand.surface(scheme), in: Circle())
      .overlay(Circle().strokeBorder(PigBrand.controlBorder(scheme), lineWidth: 1))
      .opacity(enabled ? 1 : 0.5)
      .contentShape(Circle())
  }
}

/// Song row matching the web: number or artwork, title, caption, a state mark and
/// a "more" button for song actions.
struct SongRow: View {
  let model: AppModel
  let track: Track
  var number: Int?
  var showArtwork = true
  let play: () -> Void
  @Environment(\.colorScheme) private var scheme
  private var current: Bool { model.player.queue.current?.track.id == track.id }
  private var caption: String {
    if number != nil { return track.durationText ?? track.artist }
    return [track.artist, track.album].compactMap { $0 }.filter { !$0.isEmpty }
      .joined(separator: " · ")
  }
  var body: some View {
    HStack(spacing: 12) {
      Button {
        if track.serverState == "household_available" { model.actionTrack = track } else { play() }
      } label: {
        HStack(spacing: 12) {
          if let number {
            Group {
              if current {
                Image(systemName: "waveform").foregroundStyle(PigBrand.accent(scheme))
              } else {
                Text("\(number)").foregroundStyle(.secondary)
              }
            }.font(.subheadline.monospacedDigit()).frame(width: 26)
          } else if showArtwork {
            ArtworkThumb(model: model, source: track.artworkSource, title: track.title)
          }
          VStack(alignment: .leading, spacing: 2) {
            Text(track.title).lineLimit(1)
              .foregroundStyle(current ? PigBrand.textAccent(scheme) : PigBrand.text(scheme))
            Text(caption).font(PigType.footnote).foregroundStyle(.secondary).lineLimit(1)
          }
          Spacer(minLength: 0)
        }.contentShape(Rectangle())
      }
      .buttonStyle(.plain)
      .accessibilityLabel(
        "\(track.serverState == "household_available" ? "Add" : "Play") \(track.title) by \(track.artist)"
      )
      .accessibilityValue(current ? "Now playing" : stateLabel)
      stateMark
      Button {
        model.actionTrack = track
      } label: {
        Image(systemName: "ellipsis").frame(width: 32, height: 44).foregroundStyle(.secondary)
      }.buttonStyle(.plain).accessibilityLabel("More actions for \(track.title)")
    }
    .frame(minHeight: 48)
    .contextMenu {
      Button("Song actions…", systemImage: "ellipsis.circle") { model.actionTrack = track }
    }
  }
  private var stateLabel: String {
    switch track.serverState {
    case "household_available": "Available in household"
    case "not_in_library": "Catalogue song"
    case "requested": "Requested"
    default: "In your library"
    }
  }
  @ViewBuilder private var stateMark: some View {
    switch track.serverState {
    case "household_available":
      Image(systemName: "plus.circle").foregroundStyle(PigBrand.accent(scheme))
        .accessibilityHidden(true)
    case "requested":
      Image(systemName: "clock").foregroundStyle(.secondary).accessibilityHidden(true)
    case "not_in_library":
      EmptyView()
    default:
      Image(systemName: "checkmark.circle").foregroundStyle(PigBrand.success(scheme))
        .accessibilityHidden(true)
    }
  }
}

/// Settings that belong to one album or artist sit below its music.
struct DetailSettings<Content: View>: View {
  @ViewBuilder let content: Content
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Divider()
      Text("Settings").font(.headline)
      content
    }.padding(.top, 24)
  }
}

/// Per-album or per-artist acquisition quality, the native twin of the web picker.
struct InlineQualityPicker: View {
  let model: AppModel
  let scope: String
  let id: String
  @State private var settings: QualitySettings?
  @State private var selected = "inherit"
  @State private var message: String?
  @State private var saving = false
  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      HStack {
        Text("Quality")
        Spacer()
        if let settings {
          Picker("Quality", selection: $selected) {
            Text(scope == "artist" ? "Use your default" : "Use artist or your default")
              .tag("inherit")
            ForEach(settings.options) { Text($0.label).tag($0.value) }
          }
          .labelsHidden().disabled(saving || !model.canMutate)
          .onChange(of: selected) { old, value in
            guard old != value, settings.preferences.first(where: matches)?.preferred ?? "inherit"
              != value
            else { return }
            Task { await save(value) }
          }
        } else if message == nil {
          ProgressView()
        }
      }
      if let message { Text(message).font(PigType.footnote).foregroundStyle(.secondary) }
    }
    .task(id: id) {
      guard
        let value = try? await model.readCatalogue({ try await $0.quality() })
      else {
        message = "Connect to your server to change quality."
        return
      }
      message = nil
      settings = value
      selected = value.preferences.first(where: matches)?.preferred ?? "inherit"
    }
  }
  private func matches(_ item: QualityItem) -> Bool { item.scope == scope && item.itemId == id }
  private func save(_ value: String) async {
    saving = true
    defer { saving = false }
    do {
      try await model.performPersonal {
        try await $0.saveQuality(scope: scope, id: id, preferred: value == "inherit" ? nil : value)
      }
      settings = try? await model.readCatalogue { try await $0.quality() }
      message = "Saved. Shared files keep the highest quality anyone wants."
    } catch { message = error.localizedDescription }
  }
}
