// swift-tools-version: 5.10

import PackageDescription

let package = Package(
    name: "AgentTouchBarHost",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "agent-touchbar-host", targets: ["AgentTouchBarHost"]),
    ],
    targets: [
        .executableTarget(name: "AgentTouchBarHost"),
        .testTarget(
            name: "AgentTouchBarHostTests",
            dependencies: ["AgentTouchBarHost"]
        ),
    ]
)
