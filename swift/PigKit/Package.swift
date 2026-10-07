// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "PigKit",
    platforms: [.iOS(.v18), .watchOS(.v11), .macOS(.v13)],
    products: [
        .library(name: "PigBrand", targets: ["PigBrand"]),
        .library(name: "PigAPI", targets: ["PigAPI"])
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-http-types", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-openapi-generator", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-openapi-runtime", from: "1.0.0"),
        .package(url: "https://github.com/apple/swift-openapi-urlsession", from: "1.0.0")
    ],
    targets: [
        .target(name: "PigBrand"),
        .target(name: "PigAPI", dependencies: [
            .product(name: "HTTPTypes", package: "swift-http-types"),
            .product(name: "OpenAPIRuntime", package: "swift-openapi-runtime"),
            .product(name: "OpenAPIURLSession", package: "swift-openapi-urlsession")
        ], plugins: [
            .plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")
        ]),
        .testTarget(name: "PigAPITests", dependencies: ["PigAPI"])
    ]
)
