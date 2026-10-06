// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PigNativeSpike",
    platforms: [.macOS(.v14), .iOS(.v18), .watchOS(.v11)],
    products: [.library(name: "SpikeCore", targets: ["SpikeCore"])],
    targets: [
        .target(name: "SpikeCore", path: "Shared"),
        .testTarget(name: "SpikeCoreTests", dependencies: ["SpikeCore"])
    ],
    swiftLanguageModes: [.v6]
)
