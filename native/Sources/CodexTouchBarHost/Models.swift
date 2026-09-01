import AppKit
import Foundation

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
