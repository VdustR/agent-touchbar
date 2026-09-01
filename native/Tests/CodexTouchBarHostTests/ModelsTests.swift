import Foundation
import XCTest
@testable import CodexTouchBarHost

final class ModelsTests: XCTestCase {
    func testDecodesVersionedRendererState() throws {
        let data = """
        {"schemaVersion":1,"generatedAt":"now","items":[{"id":"task:one","kind":"task","provider":"codex","label":"One","state":"active","iconProvider":"codex","action":{"type":"focusTask","taskId":"one"}}]}
        """.data(using: .utf8)!
        let state = try RendererContract.decode(data)
        XCTAssertEqual(state.items[0].action.endpoint, "/api/v1/actions/focus-task")
        XCTAssertEqual(state.items[0].action.payload, ["taskId": "one"])
        XCTAssertEqual(state.items[0].fittedWidth(font: .systemFont(ofSize: 11)), 96)
    }

    func testRejectsUnknownSchema() {
        let data = "{\"schemaVersion\":2,\"generatedAt\":\"now\",\"items\":[]}".data(using: .utf8)!
        XCTAssertThrowsError(try RendererContract.decode(data)) { error in
            XCTAssertEqual(error as? RendererContractError, .unsupportedSchema(2))
        }
    }

    func testRejectsActionWithoutTarget() {
        let data = """
        {"schemaVersion":1,"generatedAt":"now","items":[{"id":"task:one","kind":"task","provider":"codex","label":"One","state":"active","iconProvider":"codex","action":{"type":"focusTask"}}]}
        """.data(using: .utf8)!
        XCTAssertThrowsError(try RendererContract.decode(data)) { error in
            XCTAssertEqual(error as? RendererContractError, .invalidAction)
        }
    }

    func testReconcilesStableIdentityWithoutReplacingRetainedItems() throws {
        var reconciler = ItemReconciler()
        let first = try RendererContract.decode("""
        {"schemaVersion":1,"generatedAt":"now","items":[{"id":"quota:codex","kind":"quota","provider":"codex","label":"7d 75%","state":"healthy","iconProvider":"codex","action":{"type":"focusProvider","provider":"codex"}},{"id":"task:one","kind":"task","provider":"codex","label":"One","state":"active","iconProvider":"codex","action":{"type":"focusTask","taskId":"one"}}]}
        """.data(using: .utf8)!).items
        _ = reconciler.reconcile(first)
        let result = reconciler.reconcile(Array(first.reversed()))
        XCTAssertTrue(result.inserted.isEmpty)
        XCTAssertTrue(result.removed.isEmpty)
        XCTAssertEqual(result.retained, Set(["quota:codex", "task:one"]))
        XCTAssertEqual(result.orderedIds, ["task:one", "quota:codex"])
    }
}
