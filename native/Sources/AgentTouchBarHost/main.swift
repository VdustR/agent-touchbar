import AppKit
import Foundation

if CommandLine.arguments.contains("--self-test") {
    let fixture = """
    {"schemaVersion":1,"generatedAt":"now","items":[{"id":"quota:codex","kind":"quota","provider":"codex","label":"7d 75%","state":"healthy","iconProvider":"codex","action":{"type":"focusProvider","provider":"codex"}}]}
    """.data(using: .utf8)!
    do {
        let state = try RendererContract.decode(fixture)
        let capabilities = await MainActor.run { TouchBarPrivateAPI.shared.capabilities }
        let output: [String: Any] = [
            "ok": true,
            "items": state.items.count,
            "capabilities": capabilities,
        ]
        let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
        print(String(decoding: data, as: UTF8.self))
        exit(0)
    } catch {
        fputs("self-test failed: \(error)\n", stderr)
        exit(1)
    }
}

let application = NSApplication.shared
let delegate = AppDelegate()
application.delegate = delegate
application.run()
