// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "Floodlight",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "FloodlightCore"),
        .executableTarget(name: "core-selftest", dependencies: ["FloodlightCore"]),
        .executableTarget(name: "discovery-check", dependencies: ["FloodlightCore"]),
        .executableTarget(name: "Floodlight", dependencies: ["FloodlightCore"]),
    ]
)
