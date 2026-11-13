// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "probe",
    platforms: [.macOS(.v14)],
    targets: [
        .target(name: "ProbeCore"),
        .executableTarget(name: "probe", dependencies: ["ProbeCore"]),
        .executableTarget(name: "probe-selftest", dependencies: ["ProbeCore"]),
    ]
)
