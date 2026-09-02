import Foundation
import Testing
@testable import AgentTouchBarHost

@Suite("Open at login preference")
struct AppLifecycleControllerTests {
    @Test("Defaults to enabled for existing installs")
    func defaultsToEnabled() {
        let suite = "AppLifecycleControllerTests.defaults.\(UUID())"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        #expect(OpenAtLoginPreference(defaults: defaults).isEnabled)
    }

    @Test("Persists the user selection")
    func persistsSelection() {
        let suite = "AppLifecycleControllerTests.persist.\(UUID())"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let preference = OpenAtLoginPreference(defaults: defaults)

        preference.setEnabled(false)

        #expect(!OpenAtLoginPreference(defaults: defaults).isEnabled)
    }

    @Test("Updates both LaunchAgents")
    func updatesLaunchAgents() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("AppLifecycleControllerTests.\(UUID())", isDirectory: true)
        let agents = root.appendingPathComponent("Library/LaunchAgents", isDirectory: true)
        try FileManager.default.createDirectory(at: agents, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let suite = "AppLifecycleControllerTests.agents.\(UUID())"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        for label in [AppLifecycleController.bridgeLabel, AppLifecycleController.rendererLabel] {
            let data = try PropertyListSerialization.data(
                fromPropertyList: ["Label": label, "RunAtLoad": true],
                format: .xml,
                options: 0
            )
            try data.write(to: agents.appendingPathComponent("\(label).plist"))
        }
        let controller = AppLifecycleController(
            homeDirectory: root,
            preference: OpenAtLoginPreference(defaults: defaults)
        )

        try controller.setOpenAtLogin(false)

        for label in [AppLifecycleController.bridgeLabel, AppLifecycleController.rendererLabel] {
            let data = try Data(contentsOf: agents.appendingPathComponent("\(label).plist"))
            #expect(try !AppLifecycleController.runAtLoad(in: data))
        }
        #expect(!controller.opensAtLogin)
    }
}
