// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "PigKit",
    platforms: [.iOS(.v18), .watchOS(.v11), .macOS(.v13)],
    products: [.library(name: "PigBrand", targets: ["PigBrand"])],
    targets: [.target(name: "PigBrand")]
)
