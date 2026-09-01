import Foundation

final class BridgeClient: @unchecked Sendable {
    private let baseUrl: URL
    private let session: URLSession

    init(
        baseUrl: URL = URL(string: "http://127.0.0.1:4317")!,
        session: URLSession = .shared
    ) {
        self.baseUrl = baseUrl
        self.session = session
    }

    func fetchState(completion: @escaping @Sendable (Result<RendererState, Error>) -> Void) {
        var request = URLRequest(url: baseUrl.appending(path: "/api/v1/state"))
        request.timeoutInterval = 3
        session.dataTask(with: request) { data, response, error in
            completion(Self.decodeResponse(data: data, response: response, error: error))
        }.resume()
    }

    func perform(
        _ action: RendererAction,
        completion: @escaping @Sendable (Result<Void, Error>) -> Void
    ) {
        guard let payload = action.payload else {
            completion(.failure(RendererContractError.invalidAction))
            return
        }
        post(path: action.endpoint, payload: payload, completion: completion)
    }

    func heartbeat(
        capabilities: [String: Bool],
        completion: @escaping @Sendable (Result<Void, Error>) -> Void = { _ in }
    ) {
        post(
            path: "/api/v1/renderer/heartbeat",
            payload: ["capabilities": capabilities],
            completion: completion
        )
    }

    private func post(
        path: String,
        payload: [String: Any],
        completion: @escaping @Sendable (Result<Void, Error>) -> Void
    ) {
        var request = URLRequest(url: baseUrl.appending(path: path))
        request.httpMethod = "POST"
        request.timeoutInterval = 4
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        } catch {
            completion(.failure(error))
            return
        }
        session.dataTask(with: request) { data, response, error in
            if let error {
                completion(.failure(error))
                return
            }
            guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
                completion(.failure(BridgeError.badStatus))
                return
            }
            completion(.success(()))
        }.resume()
    }

    static func decodeResponse(
        data: Data?, response: URLResponse?, error: Error?
    ) -> Result<RendererState, Error> {
        if let error { return .failure(error) }
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            return .failure(BridgeError.badStatus)
        }
        guard let data else { return .failure(BridgeError.missingData) }
        do {
            return .success(try RendererContract.decode(data))
        } catch {
            return .failure(error)
        }
    }
}

enum BridgeError: Error, Equatable {
    case badStatus
    case missingData
}
