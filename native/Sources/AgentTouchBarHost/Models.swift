import AppKit
import Foundation

enum TouchBarLayout {
    static let minimumViewportWidth: CGFloat = 96
    static let maximumViewportWidth: CGFloat = 620

    static func viewportWidth(for contentWidth: CGFloat) -> CGFloat {
        min(max(ceil(contentWidth), minimumViewportWidth), maximumViewportWidth)
    }
}

struct TypographySettings: Equatable {
    static let defaultSize: CGFloat = 11

    let fontName: String?
    let fontSize: CGFloat

    static func load(defaults: UserDefaults = .standard) -> TypographySettings {
        let configuredName = defaults.string(forKey: "fontName")?.trimmingCharacters(in: .whitespacesAndNewlines)
        let configuredSize = defaults.double(forKey: "fontSize")
        return TypographySettings(
            fontName: configuredName?.isEmpty == false ? configuredName : nil,
            fontSize: (8...18).contains(configuredSize) ? configuredSize : defaultSize
        )
    }

    func font(active: Bool) -> NSFont {
        guard let fontName, let base = customFont(named: fontName) else {
            return NSFont.systemFont(ofSize: fontSize, weight: active ? .semibold : .regular)
        }
        guard active else { return base }
        let weighted = NSFontManager.shared.convertWeight(true, of: base)
        return weighted.familyName == base.familyName ? weighted : base
    }

    private func customFont(named name: String) -> NSFont? {
        if let exact = NSFont(name: name, size: fontSize) { return exact }
        guard let members = NSFontManager.shared.availableMembers(ofFontFamily: name) else { return nil }
        let regular = members.first { member in
            guard member.count > 3, let traits = member[3] as? UInt else { return false }
            return NSFontTraitMask(rawValue: traits).intersection([.boldFontMask, .italicFontMask]).isEmpty
        } ?? members.first
        guard let postScriptName = regular?.first as? String else { return nil }
        return NSFont(name: postScriptName, size: fontSize)
    }
}

enum LauncherContent: String {
    case icon
    case text
    case iconAndText
}

struct LauncherAppearance: Equatable {
    static let defaultSymbol = "terminal.fill"
    static let defaultText = "AI"

    let content: LauncherContent
    let text: String
    let symbol: String
    let iconPath: String?
    let colorHex: String?

    static func load(defaults: UserDefaults = .standard) -> LauncherAppearance {
        let content = defaults.string(forKey: "launcherContent")
            .flatMap(LauncherContent.init(rawValue:)) ?? .icon
        let text = normalized(defaults.string(forKey: "launcherText"), fallback: defaultText)
        let symbol = normalized(defaults.string(forKey: "launcherSymbol"), fallback: defaultSymbol)
        let iconPath = defaults.string(forKey: "launcherIconPath")?.trimmingCharacters(in: .whitespacesAndNewlines)
        let color = defaults.string(forKey: "launcherColor")?.trimmingCharacters(in: .whitespacesAndNewlines)
        return LauncherAppearance(
            content: content,
            text: String(text.prefix(12)),
            symbol: symbol,
            iconPath: iconPath?.isEmpty == false ? iconPath : nil,
            colorHex: color?.isEmpty == false ? color : nil
        )
    }

    var bezelColor: NSColor {
        guard let colorHex else { return .systemIndigo }
        let value = colorHex.hasPrefix("#") ? String(colorHex.dropFirst()) : colorHex
        guard value.count == 6, let rgb = UInt64(value, radix: 16) else { return .systemIndigo }
        return NSColor(
            calibratedRed: CGFloat((rgb >> 16) & 0xff) / 255,
            green: CGFloat((rgb >> 8) & 0xff) / 255,
            blue: CGFloat(rgb & 0xff) / 255,
            alpha: 1
        )
    }

    var image: NSImage? {
        let custom = iconPath
            .map { NSString(string: $0).expandingTildeInPath }
            .flatMap(NSImage.init(contentsOfFile:))
        let image = custom
            ?? NSImage(systemSymbolName: symbol, accessibilityDescription: nil)
            ?? NSImage(systemSymbolName: Self.defaultSymbol, accessibilityDescription: nil)
        image?.isTemplate = true
        return image
    }

    private static func normalized(_ value: String?, fallback: String) -> String {
        let normalized = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return normalized.isEmpty ? fallback : normalized
    }
}

struct RendererState: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let generatedAt: String
    let items: [RendererItem]

    init(schemaVersion: Int, generatedAt: String, items: [RendererItem]) {
        self.schemaVersion = schemaVersion
        self.generatedAt = generatedAt
        self.items = items
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion, generatedAt, items
    }
}

struct RendererItem: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let kind: Kind
    let provider: String
    let label: String
    let state: String
    let iconProvider: String
    let action: RendererAction

    enum Kind: String, Codable, Sendable {
        case quota
        case task
    }

    func fittedWidth(font: NSFont) -> CGFloat {
        let textWidth = (label as NSString).size(withAttributes: [.font: font]).width
        return min(max(ceil(textWidth) + 48, 96), 300)
    }
    var accessibilityLabel: String {
        let prefix = kind == .task ? "\(provider) task" : "\(provider) quota"
        return "\(prefix), \(label), \(state)"
    }
}

struct RendererAction: Codable, Equatable, Sendable {
    let type: ActionType
    let taskId: String?
    let provider: String?

    enum ActionType: String, Codable, Sendable {
        case focusTask
        case focusProvider
    }

    var endpoint: String {
        switch type {
        case .focusTask: "/api/v1/actions/focus-task"
        case .focusProvider: "/api/v1/actions/focus-provider"
        }
    }

    var payload: [String: String]? {
        switch type {
        case .focusTask:
            return taskId.map { ["taskId": $0] }
        case .focusProvider:
            return provider.map { ["provider": $0] }
        }
    }
}

enum RendererContractError: Error, Equatable {
    case unsupportedSchema(Int)
    case invalidAction
}

enum RendererContract {
    static func decode(_ data: Data) throws -> RendererState {
        let state = try JSONDecoder().decode(RendererState.self, from: data)
        guard state.schemaVersion == 1 else {
            throw RendererContractError.unsupportedSchema(state.schemaVersion)
        }
        guard state.items.allSatisfy({ $0.action.payload != nil }) else {
            throw RendererContractError.invalidAction
        }
        return state
    }
}

struct ItemReconciler {
    private(set) var orderedIds: [String] = []

    mutating func reconcile(_ items: [RendererItem]) -> ReconcileResult {
        let nextIds = items.map(\.id)
        let previous = Set(orderedIds)
        let next = Set(nextIds)
        let result = ReconcileResult(
            inserted: next.subtracting(previous),
            removed: previous.subtracting(next),
            retained: previous.intersection(next),
            orderedIds: nextIds
        )
        orderedIds = nextIds
        return result
    }
}

struct ReconcileResult: Equatable {
    let inserted: Set<String>
    let removed: Set<String>
    let retained: Set<String>
    let orderedIds: [String]
}
