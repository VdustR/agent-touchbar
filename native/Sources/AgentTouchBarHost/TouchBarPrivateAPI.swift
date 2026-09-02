import AppKit
import Darwin

@MainActor
final class TouchBarPrivateAPI {
    static let shared = TouchBarPrivateAPI()

    private typealias PresenceFunction = @convention(c) (NSString, Bool) -> Void
    private let addSelector = NSSelectorFromString("addSystemTrayItem:")
    private let removeSelector = NSSelectorFromString("removeSystemTrayItem:")
    private let presentSelectors = [
        NSSelectorFromString("presentSystemModalTouchBar:systemTrayItemIdentifier:"),
        NSSelectorFromString("presentSystemModalFunctionBar:systemTrayItemIdentifier:"),
    ]
    private let dismissSelectors = [
        NSSelectorFromString("dismissSystemModalTouchBar:"),
        NSSelectorFromString("dismissSystemModalFunctionBar:"),
    ]
    private let framework: UnsafeMutableRawPointer?
    private let presence: PresenceFunction?

    private init() {
        framework = dlopen(
            "/System/Library/PrivateFrameworks/DFRFoundation.framework/DFRFoundation",
            RTLD_LAZY
        )
        if let framework,
           let symbol = dlsym(framework, "DFRElementSetControlStripPresenceForIdentifier") {
            presence = unsafeBitCast(symbol, to: PresenceFunction.self)
        } else {
            presence = nil
        }
    }

    var supportsControlStrip: Bool {
        presence != nil && (NSTouchBarItem.self as AnyObject).responds(to: addSelector)
    }

    var supportsSystemModal: Bool {
        presentSelectors.contains { (NSTouchBar.self as AnyObject).responds(to: $0) }
    }

    var supportsSystemModalDismiss: Bool {
        dismissSelectors.contains { (NSTouchBar.self as AnyObject).responds(to: $0) }
    }

    var capabilities: [String: Bool] {
        [
            "controlStrip": supportsControlStrip,
            "systemModal": supportsSystemModal,
            "systemModalDismiss": supportsSystemModalDismiss,
            "publicTouchBar": true,
        ]
    }

    func installControlStripItem(_ item: NSTouchBarItem) {
        guard supportsControlStrip else { return }
        _ = (NSTouchBarItem.self as AnyObject).perform(addSelector, with: item)
        presence?(item.identifier.rawValue as NSString, true)
    }

    func removeControlStripItem(_ item: NSTouchBarItem) {
        guard supportsControlStrip else { return }
        presence?(item.identifier.rawValue as NSString, false)
        _ = (NSTouchBarItem.self as AnyObject).perform(removeSelector, with: item)
    }

    @discardableResult
    func present(_ touchBar: NSTouchBar, trayIdentifier: NSTouchBarItem.Identifier) -> Bool {
        guard let selector = presentSelectors.first(where: {
            (NSTouchBar.self as AnyObject).responds(to: $0)
        }) else { return false }
        _ = (NSTouchBar.self as AnyObject).perform(
            selector,
            with: touchBar,
            with: trayIdentifier.rawValue
        )
        return true
    }

    @discardableResult
    func dismiss(_ touchBar: NSTouchBar) -> Bool {
        guard let selector = dismissSelectors.first(where: {
            (NSTouchBar.self as AnyObject).responds(to: $0)
        }) else { return false }
        _ = (NSTouchBar.self as AnyObject).perform(selector, with: touchBar)
        return true
    }
}
