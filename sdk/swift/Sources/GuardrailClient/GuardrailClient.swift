import Foundation

#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

/// HTTP error carrying the gateway's JSON `detail` when available.
public struct ApiError: Error, LocalizedError, Sendable {
    public let statusCode: Int
    public let detail: String

    public var errorDescription: String? { "HTTP \(statusCode): \(detail)" }
}

/// Mirrors `GuardrailResult` from the gateway OpenAPI schema.
public struct GuardrailResult: Codable, Sendable, Equatable {
    public let passed: Bool
    public let check: String
    public let reason: String
    public let reasonCode: String?
    public let riskScore: Double

    enum CodingKeys: String, CodingKey {
        case passed, check, reason
        case reasonCode = "reason_code"
        case riskScore = "risk_score"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        passed = try c.decodeIfPresent(Bool.self, forKey: .passed) ?? true
        check = try c.decodeIfPresent(String.self, forKey: .check) ?? ""
        reason = try c.decodeIfPresent(String.self, forKey: .reason) ?? ""
        reasonCode = try c.decodeIfPresent(String.self, forKey: .reasonCode)
        riskScore = try c.decodeIfPresent(Double.self, forKey: .riskScore) ?? 0
    }
}

/// Mirrors `ChatResponse` from the gateway OpenAPI schema.
public struct ChatResponse: Codable, Sendable {
    public let requestId: String
    public let response: String?
    public let status: String
    public let inputGuard: GuardrailResult
    public let outputGuard: GuardrailResult?
    public let latencyMs: Int
    public let model: String
    public let backend: String
    public let tokensRemaining: Int?

    enum CodingKeys: String, CodingKey {
        case requestId = "request_id"
        case response, status
        case inputGuard = "input_guard"
        case outputGuard = "output_guard"
        case latencyMs = "latency_ms"
        case model, backend
        case tokensRemaining = "tokens_remaining"
    }
}

/// SSE events from `/chat/stream` — mirrors the JS/Python/Kotlin SDKs.
public enum StreamEvent: Sendable, Equatable {
    case token(content: String)
    case done(status: String, model: String, backend: String, latencyMs: Int,
              inputGuard: GuardrailResult, outputGuard: GuardrailResult?)
    case blocked(status: String, inputGuard: GuardrailResult?, outputGuard: GuardrailResult?)
    case error(detail: String)
    case ping
}

/// Client for the LLM Guardrails gateway — API-identical to
/// `sdk/javascript/guardrailClient.mjs`, `sdk/python/guardrail_client.py`,
/// and `sdk/kotlin`. Auth is the `X-Api-Key` header.
///
/// - Important: Do NOT ship a gateway API key inside a mobile app. Keys are
///   trivially extractable from installed binaries. See README.md — prefer
///   routing requests through your own backend.
public final class GuardrailClient: @unchecked Sendable {
    private let baseURL: URL
    private let apiKey: String
    private let session: URLSession
    private let withRetry: Bool
    private let maxRetries: Int

    public init(
        baseURL: String,
        apiKey: String,
        session: URLSession = .shared,
        withRetry: Bool = false,
        maxRetries: Int = 3
    ) throws {
        guard let url = URL(string: baseURL.trimmingCharacters(in: CharacterSet(charactersIn: "/"))) else {
            throw ApiError(statusCode: 0, detail: "invalid base URL")
        }
        self.baseURL = url
        self.apiKey = apiKey
        self.session = session
        self.withRetry = withRetry
        self.maxRetries = maxRetries
    }

    // MARK: - Non-streaming chat

    public func chat(
        prompt: String,
        model: String? = nil,
        backend: String? = nil,
        temperature: Double = 0.7,
        maxTokens: Int = 256
    ) async throws -> ChatResponse {
        let payload = payload(prompt: prompt, model: model, backend: backend,
                              temperature: temperature, maxTokens: maxTokens)
        let retries = withRetry ? maxRetries : 0

        for attempt in 1...max(1, retries + 1) {
            var request = try makeRequest(path: "/chat", body: payload)
            let (data, response) = try await session.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0

            if (status == 402 || status == 429) && attempt <= retries {
                try await Task.sleep(nanoseconds: await retryDelay(for: response, attempt: attempt))
                continue
            }
            guard (200...299).contains(status) else {
                throw try error(from: status, data: data)
            }
            return try JSONDecoder().decode(ChatResponse.self, from: data)
        }
        throw ApiError(statusCode: 0, detail: "unreachable")
    }

    // MARK: - Streaming chat

    /// SSE stream from `/chat/stream`. Retries only happen before the first
    /// event arrives; after that the stream is never retried.
    public func chatStream(
        prompt: String,
        model: String? = nil,
        backend: String? = nil,
        temperature: Double = 0.7,
        maxTokens: Int = 256
    ) async throws -> AsyncThrowingStream<StreamEvent, Error> {
        let payload = payload(prompt: prompt, model: model, backend: backend,
                              temperature: temperature, maxTokens: maxTokens)
        let retries = withRetry ? maxRetries : 0
        var bytes: URLSession.AsyncBytes? = nil
        var status = 0

        for attempt in 1...max(1, retries + 1) {
            var request = try makeRequest(path: "/chat/stream", body: payload)
            request.timeoutInterval = 30
            let (streamBytes, response) = try await session.bytes(for: request)
            status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if (status == 402 || status == 429) && attempt <= retries {
                try await Task.sleep(nanoseconds: await retryDelay(for: response, attempt: attempt))
                continue
            }
            bytes = streamBytes
            break
        }

        guard let bytes, (200...299).contains(status) else {
            var data = Data()
            if let bytes {
                for try await line in bytes.lines where line.hasPrefix("data: ") {
                    data.append(contentsOf: line.dropFirst(6).utf8)
                }
            }
            throw try error(from: status, data: data)
        }

        return AsyncThrowingStream { continuation in
            Task {
                do {
                    for try await line in bytes.lines where line.hasPrefix("data: ") {
                        let event = try Self.parseEvent(json: String(line.dropFirst(6)))
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
        }
    }

    // MARK: - Internals

    private func payload(prompt: String, model: String?, backend: String?,
                         temperature: Double, maxTokens: Int) -> [String: Any] {
        var body: [String: Any] = ["prompt": prompt, "temperature": temperature, "max_tokens": maxTokens]
        if let model, !model.isEmpty { body["model"] = model }
        if let backend, !backend.isEmpty { body["backend"] = backend }
        return body
    }

    private func makeRequest(path: String, body: [String: Any]) throws -> URLRequest {
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(apiKey, forHTTPHeaderField: "X-Api-Key")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        return request
    }

    private static func parseEvent(json: String) throws -> StreamEvent {
        struct Raw: Decodable {
            let type: String?
            let content: String?
            let status: String?
            let model: String?
            let backend: String?
            let detail: String?
            let latencyMs: Int?
            let inputGuard: GuardrailResult?
            let outputGuard: GuardrailResult?

            enum CodingKeys: String, CodingKey {
                case type, content, status, model, backend, detail
                case latencyMs = "latency_ms"
                case inputGuard = "input_guard"
                case outputGuard = "output_guard"
            }
        }
        guard let data = json.data(using: .utf8) else { return .ping }
        let raw = try JSONDecoder().decode(Raw.self, from: data)
        switch raw.type {
        case "token": return .token(content: raw.content ?? "")
        case "done": return .done(
            status: raw.status ?? "delivered", model: raw.model ?? "", backend: raw.backend ?? "",
            latencyMs: raw.latencyMs ?? 0, inputGuard: raw.inputGuard ?? .init(passed: true, check: "", reason: "", reasonCode: nil, riskScore: 0),
            outputGuard: raw.outputGuard)
        case "blocked": return .blocked(status: raw.status ?? "blocked", inputGuard: raw.inputGuard, outputGuard: raw.outputGuard)
        case "error": return .error(detail: raw.detail ?? "unknown error")
        default: return .ping
        }
    }

    private func retryDelay(for response: URLResponse, attempt: Int) async -> UInt64 {
        if let http = response as? HTTPURLResponse,
           let raw = http.value(forHTTPHeaderField: "Retry-After"),
           let seconds = Double(raw) {
            return UInt64(seconds * 1_000_000_000)
        }
        let base = Double(min(1 << (attempt - 1), 8))
        return UInt64(base * 1_000_000_000)
    }

    private func error(from status: Int, data: Data) throws -> ApiError {
        struct Body: Decodable { let detail: String? }
        let detail = (try? JSONDecoder().decode(Body.self, from: data))?.detail
            ?? String(data: data, encoding: .utf8)?.prefix(200).description
            ?? "request failed"
        return ApiError(statusCode: status, detail: detail)
    }
}
