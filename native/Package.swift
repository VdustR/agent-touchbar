// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "CodexTouchBarHost",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "codex-touchbar-host", targets: ["CodexTouchBarHost"]),
    ],
    targets: [
        .executableTarget(name: "CodexTouchBarHost"),
        .testTarget(
            name: "CodexTouchBarHostTests",
            dependencies: ["CodexTouchBarHost"]
        ),
    ]
)
