import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let bridge = BridgeClient()
    private lazy var touchBarController = TouchBarController(bridge: bridge)
    private var statusItem: NSStatusItem?
    private var refreshTimer: Timer?
    private var heartbeatTimer: Timer?
    private var lastItems: [RendererItem]?
    private var refreshInFlight = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        configureStatusItem()
        _ = touchBarController
        refresh()
        if ProcessInfo.processInfo.environment["CODEXBAR_TOUCHBAR_PRESENT_ON_LAUNCH"] == "1" {
            touchBarController.showTouchBar()
        }
        refreshTimer = Timer.scheduledTimer(
            timeInterval: 1,
            target: self,
            selector: #selector(refreshTimerFired),
            userInfo: nil,
            repeats: true
        )
        heartbeat()
        heartbeatTimer = Timer.scheduledTimer(
            timeInterval: 4,
            target: self,
            selector: #selector(heartbeatTimerFired),
            userInfo: nil,
            repeats: true
        )
        NSWorkspace.shared.notificationCenter.addObserver(
            self,
            selector: #selector(didWake),
            name: NSWorkspace.didWakeNotification,
            object: nil
        )
    }

    func applicationWillTerminate(_ notification: Notification) {
        refreshTimer?.invalidate()
        heartbeatTimer?.invalidate()
        NSWorkspace.shared.notificationCenter.removeObserver(self)
        touchBarController.shutdown()
    }

    private func configureStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        item.button?.title = "AI"
        item.button?.toolTip = "Coding agent Touch Bar"
        let menu = NSMenu()
        let status = NSMenuItem(title: "Waiting for local bridge", action: nil, keyEquivalent: "")
        status.tag = 1
        menu.addItem(status)
        menu.addItem(NSMenuItem(
            title: "Show Touch Bar",
            action: #selector(showTouchBar),
            keyEquivalent: ""
        ))
        item.menu = menu
        statusItem = item
    }

    private func refresh() {
        guard !refreshInFlight else { return }
        refreshInFlight = true
        bridge.fetchState { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                self.refreshInFlight = false
                switch result {
                case .success(let state):
                    if state.items != self.lastItems {
                        self.touchBarController.update(state)
                        self.lastItems = state.items
                    }
                    self.setStatus("Native renderer · \(state.items.count) items")
                case .failure:
                    self.setStatus("Bridge unavailable")
                }
            }
        }
    }

    private func heartbeat() {
        bridge.heartbeat(capabilities: TouchBarPrivateAPI.shared.capabilities)
    }

    private func setStatus(_ title: String) {
        statusItem?.menu?.item(withTag: 1)?.title = title
    }

    @objc private func didWake() {
        refresh()
        heartbeat()
    }

    @objc private func refreshTimerFired() {
        refresh()
    }

    @objc private func heartbeatTimerFired() {
        heartbeat()
    }

    @objc private func showTouchBar() {
        touchBarController.showTouchBar()
    }

}
