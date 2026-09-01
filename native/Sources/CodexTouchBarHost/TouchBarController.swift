import AppKit

private extension NSTouchBarItem.Identifier {
    static let nativeContent = NSTouchBarItem.Identifier("com.vdustr.codexbar-touchbar.content")
    static let nativeControlStrip = NSTouchBarItem.Identifier("com.vdustr.codexbar-touchbar.control-strip")
}

@MainActor
final class TouchBarController: NSObject, NSTouchBarDelegate {
    let touchBar = NSTouchBar()
    private let bridge: BridgeClient
    private let scrollView = NSScrollView()
    private let stackView = NSStackView()
    private var viewportWidthConstraint: NSLayoutConstraint?
    private var buttons: [String: ActionButton] = [:]
    private var reconciler = ItemReconciler()
    private var controlStripItem: NSCustomTouchBarItem?
    private var launcherButton: NSButton?
    private(set) var typography = TypographySettings.load()
    private(set) var launcherAppearance = LauncherAppearance.load()

    init(bridge: BridgeClient) {
        self.bridge = bridge
        super.init()
        configureTouchBar()
        installControlStrip()
    }

    func shutdown() {
        if let controlStripItem {
            TouchBarPrivateAPI.shared.removeControlStripItem(controlStripItem)
            self.controlStripItem = nil
        }
    }

    private func configureTouchBar() {
        touchBar.delegate = self
        touchBar.customizationIdentifier = NSTouchBar.CustomizationIdentifier(
            "com.vdustr.codexbar-touchbar.native"
        )
        touchBar.defaultItemIdentifiers = [.nativeContent]
        touchBar.customizationRequiredItemIdentifiers = [.nativeContent]

        stackView.orientation = .horizontal
        stackView.alignment = .centerY
        stackView.spacing = 2
        stackView.edgeInsets = NSEdgeInsets(top: 1, left: 2, bottom: 1, right: 2)
        stackView.translatesAutoresizingMaskIntoConstraints = false

        scrollView.hasHorizontalScroller = false
        scrollView.hasVerticalScroller = false
        scrollView.drawsBackground = false
        scrollView.documentView = stackView
        scrollView.frame = NSRect(x: 0, y: 0, width: 96, height: 30)
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        viewportWidthConstraint = scrollView.widthAnchor.constraint(
            equalToConstant: TouchBarLayout.minimumViewportWidth
        )
        NSLayoutConstraint.activate([
            viewportWidthConstraint!,
            scrollView.heightAnchor.constraint(equalToConstant: 30),
            stackView.heightAnchor.constraint(equalToConstant: 28),
            stackView.leadingAnchor.constraint(equalTo: scrollView.contentView.leadingAnchor),
            stackView.topAnchor.constraint(equalTo: scrollView.contentView.topAnchor),
        ])
    }

    private func installControlStrip() {
        guard TouchBarPrivateAPI.shared.supportsControlStrip else { return }
        let item = NSCustomTouchBarItem(identifier: .nativeControlStrip)
        let button = NSButton(title: "", target: self, action: #selector(showTouchBar))
        button.toolTip = "Coding agent tasks and quota"
        button.setAccessibilityLabel("Open coding agent tasks and quota")
        launcherButton = button
        configureLauncherButton()
        item.view = button
        item.customizationLabel = "Coding agents"
        controlStripItem = item
        TouchBarPrivateAPI.shared.installControlStripItem(item)
    }

    func touchBar(
        _ touchBar: NSTouchBar,
        makeItemForIdentifier identifier: NSTouchBarItem.Identifier
    ) -> NSTouchBarItem? {
        guard identifier == .nativeContent else { return nil }
        let item = NSCustomTouchBarItem(identifier: identifier)
        item.view = scrollView
        item.customizationLabel = "Coding agent tasks and quota"
        return item
    }

    func update(_ state: RendererState) {
        typography = TypographySettings.load()
        launcherAppearance = LauncherAppearance.load()
        configureLauncherButton()
        let offset = scrollView.contentView.bounds.origin
        let result = reconciler.reconcile(state.items)

        for id in result.removed {
            if let button = buttons.removeValue(forKey: id) {
                stackView.removeArrangedSubview(button)
                button.removeFromSuperview()
            }
        }
        for item in state.items {
            let button = buttons[item.id] ?? ActionButton()
            if buttons[item.id] == nil {
                buttons[item.id] = button
            }
            configure(button, for: item)
        }
        for view in stackView.arrangedSubviews {
            stackView.removeArrangedSubview(view)
            view.removeFromSuperview()
        }
        for id in result.orderedIds {
            if let button = buttons[id] { stackView.addArrangedSubview(button) }
        }
        stackView.layoutSubtreeIfNeeded()
        let contentWidth = stackView.fittingSize.width
        viewportWidthConstraint?.constant = TouchBarLayout.viewportWidth(for: contentWidth)
        scrollView.contentView.scroll(to: offset)
        scrollView.reflectScrolledClipView(scrollView.contentView)
    }

    private func configureLauncherButton() {
        guard let button = launcherButton else { return }
        button.bezelColor = launcherAppearance.bezelColor
        switch launcherAppearance.content {
        case .icon:
            button.title = ""
            button.image = launcherAppearance.image
            button.imagePosition = .imageOnly
        case .text:
            button.title = launcherAppearance.text
            button.image = nil
            button.imagePosition = .noImage
        case .iconAndText:
            button.title = launcherAppearance.text
            button.image = launcherAppearance.image
            button.imagePosition = .imageLeading
        }
    }

    private func configure(_ button: ActionButton, for item: RendererItem) {
        button.title = displayTitle(for: item)
        button.rendererAction = item.action
        button.target = self
        button.action = #selector(runAction(_:))
        button.bezelStyle = .rounded
        button.isBordered = true
        button.lineBreakMode = .byTruncatingTail
        button.cell?.wraps = false
        button.cell?.usesSingleLineMode = true
        let font = typography.font(active: item.state == "active")
        button.font = font
        button.image = appIcon(provider: item.iconProvider)
        button.imagePosition = .imageLeading
        button.imageScaling = .scaleProportionallyDown
        button.bezelColor = color(for: item.state)
        button.toolTip = item.accessibilityLabel
        button.setAccessibilityLabel(item.accessibilityLabel)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.updateSize(width: item.fittedWidth(font: font), height: 26)
    }

    private func displayTitle(for item: RendererItem) -> String {
        guard item.kind == .task else { return item.label }
        let marker = ["active": "●", "idle": "○", "available": "○"]
            .first { $0.key == item.state }?.value ?? "!"
        return "\(marker) \(item.label)"
    }

    private func color(for state: String) -> NSColor {
        switch state {
        case "active", "healthy": NSColor(calibratedRed: 0.12, green: 0.36, blue: 0.28, alpha: 1)
        case "warning": NSColor(calibratedRed: 0.55, green: 0.34, blue: 0.10, alpha: 1)
        case "critical", "needs_input", "attention", "blocked", "waiting", "approval_required":
            NSColor(calibratedRed: 0.52, green: 0.16, blue: 0.19, alpha: 1)
        default: NSColor(calibratedRed: 0.16, green: 0.19, blue: 0.24, alpha: 1)
        }
    }

    private func appIcon(provider: String) -> NSImage? {
        let names = ["codex": "ChatGPT", "claude": "Claude", "antigravity": "Antigravity"]
        guard let name = names[provider] else { return nil }
        let fallback = URL(fileURLWithPath: "/Applications/\(name).app")
        let url = NSWorkspace.shared.urlForApplication(withBundleIdentifier: bundleId(for: provider))
            ?? (FileManager.default.fileExists(atPath: fallback.path) ? fallback : nil)
        guard let url else { return nil }
        let image = NSWorkspace.shared.icon(forFile: url.path)
        image.size = NSSize(width: 18, height: 18)
        return image
    }

    private func bundleId(for provider: String) -> String {
        [
            "codex": "com.openai.codex",
            "claude": "com.anthropic.claudefordesktop",
            "antigravity": "com.google.antigravity",
        ][provider] ?? ""
    }

    @objc private func runAction(_ sender: ActionButton) {
        guard let action = sender.rendererAction else { return }
        sender.isEnabled = false
        bridge.perform(action) { result in
            DispatchQueue.main.async {
                sender.isEnabled = true
                if case .failure = result { NSSound.beep() }
            }
        }
    }

    @objc func showTouchBar() {
        TouchBarPrivateAPI.shared.present(
            touchBar,
            trayIdentifier: .nativeControlStrip
        )
    }
}

final class ActionButton: NSButton {
    var rendererAction: RendererAction?
    private var fixedWidthConstraint: NSLayoutConstraint?
    private var fixedHeightConstraint: NSLayoutConstraint?

    func updateSize(width: CGFloat, height: CGFloat) {
        if fixedWidthConstraint == nil {
            fixedWidthConstraint = widthAnchor.constraint(equalToConstant: width)
            fixedWidthConstraint?.isActive = true
        } else {
            fixedWidthConstraint?.constant = width
        }
        if fixedHeightConstraint == nil {
            fixedHeightConstraint = heightAnchor.constraint(equalToConstant: height)
            fixedHeightConstraint?.isActive = true
        } else {
            fixedHeightConstraint?.constant = height
        }
    }
}
