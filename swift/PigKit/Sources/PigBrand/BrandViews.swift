import SwiftUI

/// Decorative radiance stays behind content; accessibility can request a solid canvas.
public struct PigCanvasBackground: View {
  @Environment(\.colorScheme) private var scheme
  @Environment(\.layoutDirection) private var direction
  @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
  public init() {}
  public var body: some View {
    GeometryReader { geometry in
      PigBrand.canvas(scheme)
        .overlay {
          if !reduceTransparency {
            RadialGradient(
              colors: [PigBrand.accent(.dark).opacity(scheme == .dark ? 0.13 : 0.16), .clear],
              center: direction == .rightToLeft ? .topTrailing : .topLeading,
              startRadius: 0,
              endRadius: hypot(geometry.size.width, geometry.size.height) * 0.62)
          }
        }
    }.ignoresSafeArea().accessibilityHidden(true).allowsHitTesting(false)
  }
}

private struct BrandCanvas: ViewModifier {
  @Environment(\.colorScheme) private var scheme
  func body(content: Content) -> some View {
    content.scrollContentBackground(.hidden)
      .foregroundStyle(PigBrand.text(scheme), PigBrand.secondary(scheme))
      .tint(PigBrand.accent(scheme))
      .background { PigCanvasBackground() }
  }
}

private struct FloatingControls: ViewModifier {
  @Environment(\.colorScheme) private var scheme
  @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
  @Environment(\.colorSchemeContrast) private var contrast
  @ViewBuilder func body(content: Content) -> some View {
    if #available(iOS 26, watchOS 26, macOS 26, tvOS 26, *), !reduceTransparency {
      content.glassEffect(.regular, in: Capsule())
        .overlay {
          if contrast == .increased {
            Capsule().strokeBorder(PigBrand.controlBorder(scheme), lineWidth: 1)
          }
        }
    } else {
      content.background(PigBrand.surface(scheme), in: Capsule())
        .overlay { Capsule().strokeBorder(PigBrand.controlBorder(scheme), lineWidth: 1) }
    }
  }
}

private struct PrimaryAction: ViewModifier {
  @Environment(\.colorScheme) private var scheme
  @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
  @ViewBuilder func body(content: Content) -> some View {
    if #available(iOS 26, watchOS 26, macOS 26, tvOS 26, *), !reduceTransparency {
      content.buttonStyle(.glassProminent).tint(PigBrand.accent(scheme))
        .foregroundStyle(PigBrand.onAccent(scheme))
    } else {
      content.buttonStyle(.borderedProminent).tint(PigBrand.accent(scheme))
        .foregroundStyle(PigBrand.onAccent(scheme))
    }
  }
}

extension View {
  public func pigBrandedCanvas() -> some View { modifier(BrandCanvas()) }
  public func pigFloatingControls() -> some View { modifier(FloatingControls()) }
  public func pigPrimaryAction() -> some View { modifier(PrimaryAction()) }
  @ViewBuilder public func pigContentCorners() -> some View {
    if #available(iOS 26, watchOS 26, macOS 26, tvOS 26, *) {
      clipShape(ConcentricRectangle())
    } else {
      clipShape(RoundedRectangle(cornerRadius: 16))
    }
  }
}

/// Matches the static launch composition; disappears immediately when restoration finishes.
public struct PigBrandSplash: View {
  @Environment(\.colorScheme) private var scheme
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
  @State private var bloom = false
  private let size: CGFloat
  public init(size: CGFloat = 180) { self.size = size }
  public var body: some View {
    ZStack {
      PigBrand.canvas(scheme).ignoresSafeArea()
      ZStack {
        if !reduceTransparency {
          Image("PigHalo").resizable().scaledToFit()
            .opacity(reduceMotion ? 1 : (bloom ? 0.25 : 1))
          if !reduceMotion {
            RadialGradient(
              colors: [PigBrand.accent(.dark).opacity(scheme == .dark ? 0.46 : 0.3), .clear],
              center: .center, startRadius: 0, endRadius: size * 0.68
            ).opacity(bloom ? 1 : 0).scaleEffect(bloom ? 1.12 : 0.9)
          }
        }
        Image("PigIconBody").resizable().scaledToFit()
        Image("PigIconFace").resizable().scaledToFit()
      }.frame(width: size, height: size)
    }
    .accessibilityElement(children: .ignore).accessibilityLabel("Pig Music is loading")
    .onAppear {
      guard !reduceMotion && !reduceTransparency else { return }
      withAnimation(.easeInOut(duration: 4).repeatForever(autoreverses: true)) { bloom = true }
    }
  }
}
