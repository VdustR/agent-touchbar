import Foundation

struct OpenAtLoginPreference {
    static let key = "openAtLogin"

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    var isEnabled: Bool {
        guard defaults.object(forKey: Self.key) != nil else { return true }
        return defaults.bool(forKey: Self.key)
    }

    func setEnabled(_ enabled: Bool) {
        defaults.set(enabled, forKey: Self.key)
    }
}

final class AppLifecycleController {
    static let bridgeLabel = "com.vdustr.agent-touchbar"
    static let rendererLabel = "com.vdustr.agent-touchbar.renderer"

    private let fileManager: FileManager
    private let homeDirectory: URL
    private let preference: OpenAtLoginPreference

    init(
        fileManager: FileManager = .default,
        homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser,
        preference: OpenAtLoginPreference = OpenAtLoginPreference()
    ) {
        self.fileManager = fileManager
        self.homeDirectory = homeDirectory
        self.preference = preference
    }

    var opensAtLogin: Bool { preference.isEnabled }

    func setOpenAtLogin(_ enabled: Bool) throws {
        let urls = [launchAgentURL(label: Self.bridgeLabel), launchAgentURL(label: Self.rendererLabel)]
            .filter { fileManager.fileExists(atPath: $0.path) }
        let originals = try Dictionary(uniqueKeysWithValues: urls.map { url in
            (url, try Data(contentsOf: url))
        })
        var written: [URL] = []
        do {
            for url in urls {
                var plist = try propertyList(data: originals[url]!)
                plist["RunAtLoad"] = enabled
                let data = try PropertyListSerialization.data(
                    fromPropertyList: plist,
                    format: .xml,
                    options: 0
                )
                try data.write(to: url, options: .atomic)
                written.append(url)
            }
        } catch {
            for url in written {
                try? originals[url]?.write(to: url, options: .atomic)
            }
            throw error
        }
        preference.setEnabled(enabled)
    }

    static func runAtLoad(in data: Data) throws -> Bool {
        let plist = try propertyList(data: data)
        return plist["RunAtLoad"] as? Bool ?? true
    }

    private static func propertyList(data: Data) throws -> [String: Any] {
        guard let plist = try PropertyListSerialization.propertyList(
            from: data,
            options: [],
            format: nil
        ) as? [String: Any] else {
            throw CocoaError(.propertyListReadCorrupt)
        }
        return plist
    }

    private func propertyList(data: Data) throws -> [String: Any] {
        try Self.propertyList(data: data)
    }

    func ensureBridgeRunning() {
        if !isLoaded(label: Self.bridgeLabel) {
            let url = launchAgentURL(label: Self.bridgeLabel)
            guard fileManager.fileExists(atPath: url.path) else { return }
            guard runLaunchctl(["bootstrap", domain, url.path]) else { return }
        }
        _ = runLaunchctl(["kickstart", "\(domain)/\(Self.bridgeLabel)"])
    }

    func quit(completion: @escaping () -> Void) {
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            _ = runLaunchctl(["bootout", "\(domain)/\(Self.bridgeLabel)"])
            _ = runLaunchctl([
                "bootout", "\(domain)/\(Self.rendererLabel)",
            ])
            DispatchQueue.main.async(execute: completion)
        }
    }

    private var domain: String { "gui/\(getuid())" }

    private func launchAgentURL(label: String) -> URL {
        homeDirectory
            .appendingPathComponent("Library/LaunchAgents", isDirectory: true)
            .appendingPathComponent("\(label).plist")
    }

    private func isLoaded(label: String) -> Bool {
        runLaunchctl(["print", "\(domain)/\(label)"])
    }

    @discardableResult
    private func runLaunchctl(_ arguments: [String]) -> Bool {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        process.arguments = arguments
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            process.waitUntilExit()
            return process.terminationStatus == 0
        } catch {
            return false
        }
    }
}
