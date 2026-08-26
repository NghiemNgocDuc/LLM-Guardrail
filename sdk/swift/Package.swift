// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "GuardrailClient",
    platforms: [
        .iOS(.v16),
        .macOS(.v13),
    ],
    products: [
        .library(name: "GuardrailClient", targets: ["GuardrailClient"]),
    ],
    targets: [
        .target(name: "GuardrailClient"),
        .testTarget(name: "GuardrailClientTests", dependencies: ["GuardrailClient"]),
    ]
)
