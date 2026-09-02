import Foundation
import XCTest
@testable import AgentTouchBarHost

final class AppLifecycleControllerTests: XCTestCase {
    func testOpenAtLoginDefaultsToEnabled() {
        let suite = "AppLifecycleControllerTests.defaults.\(UUID())"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        XCTAssertTrue(OpenAtLoginPreference(defaults: defaults).isEnabled)
    }

    func testOpenAtLoginPersistsUserSelection() {
        let suite = "AppLifecycleControllerTests.persist.\(UUID())"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let preference = OpenAtLoginPreference(defaults: defaults)

        preference.setEnabled(false)

        XCTAssertFalse(OpenAtLoginPreference(defaults: defaults).isEnabled)
    }

    func testOpenAtLoginUpdatesBothLaunchAgents() throws {
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
            XCTAssertFalse(try AppLifecycleController.runAtLoad(in: data))
        }
        XCTAssertFalse(controller.opensAtLogin)
    }
}
