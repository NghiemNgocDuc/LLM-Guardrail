import XCTest
@testable import GuardrailClient

/// Intercepts URLSession traffic and serves canned gateway responses —
/// no network access required, so the tests run anywhere Swift does.
final class MockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?
    nonisolated(unsafe) static var requestCount = 0
    nonisolated(unsafe) static var lastAuthHeader: String?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        MockURLProtocol.requestCount += 1
        MockURLProtocol.lastAuthHeader = request.value(forHTTPHeaderField: "X-Api-Key")
        do {
            let (response, data) = try MockURLProtocol.handler!(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class GuardrailClientTests: XCTestCase {
    var client: GuardrailClient!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        MockURLProtocol.requestCount = 0
        MockURLProtocol.lastAuthHeader = nil
        client = try! GuardrailClient(
            baseURL: "https://gateway.example.com",
            apiKey: "test-key-123",
            session: URLSession(configuration: config),
            withRetry: true,
            maxRetries: 2
        )
    }

    private func json(_ value: String) -> (HTTPURLResponse, Data) {
        let response = HTTPURLResponse(
            url: URL(string: "https://gateway.example.com")!, statusCode: 200,
            httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
        return (response, Data(value.utf8))
    }

    private func sse(_ lines: [String]) -> (HTTPURLResponse, Data) {
        let body = lines.map { "data: \($0)\n\n" }.joined()
        let response = HTTPURLResponse(
            url: URL(string: "https://gateway.example.com")!, statusCode: 200,
            httpVersion: nil, headerFields: ["Content-Type": "text/event-stream"])!
        return (response, Data(body.utf8))
    }

    // MARK: - Non-streaming

    func testChatParsesDeliveredResponse() async throws {
        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(MockURLProtocol.lastAuthHeader, "test-key-123")
            let body = String(data: request.httpBody!, encoding: .utf8)!
            XCTAssertTrue(body.contains("\"prompt\":\"hello\""))
            XCTAssertTrue(body.contains("\"max_tokens\":256"))
            return self.json("""
                {"request_id":"req-1","response":"Hi there","status":"delivered",
                 "input_guard":{"passed":true,"check":"Input Checks","reason":"","reason_code":null,"risk_score":0.0},
                 "output_guard":{"passed":true,"check":"Output Checks","reason":"","reason_code":null,"risk_score":0.0},
                 "latency_ms":42,"model":"gpt-test","backend":"openai","tokens_remaining":999}
                """)
        }
        let result = try await client.chat(prompt: "hello")
        XCTAssertEqual(result.status, "delivered")
        XCTAssertEqual(result.response, "Hi there")
        XCTAssertEqual(result.requestId, "req-1")
        XCTAssertEqual(result.latencyMs, 42)
        XCTAssertEqual(result.tokensRemaining, 999)
        XCTAssertTrue(result.inputGuard.passed)
        XCTAssertEqual(result.outputGuard?.check, "Output Checks")
    }

    func testChatRetriesOn429WithRetryAfter() async throws {
        var calls = 0
        MockURLProtocol.handler = { _ in
            calls += 1
            if calls == 1 {
                let response = HTTPURLResponse(
                    url: URL(string: "https://gateway.example.com")!, statusCode: 429,
                    httpVersion: nil, headerFields: ["Retry-After": "0"])!
                return (response, Data("{\"detail\":\"rate limited\"}".utf8))
            }
            return self.json("""
                {"request_id":"req-2","response":"ok","status":"delivered",
                 "input_guard":{"passed":true,"check":"Input","reason":"","reason_code":null,"risk_score":0.0},
                 "latency_ms":1,"model":"m","backend":"b","tokens_remaining":null}
                """)
        }
        let result = try await client.chat(prompt: "retry me")
        XCTAssertEqual(result.status, "delivered")
        XCTAssertEqual(calls, 2)
    }

    func testChatSurfaces429WithoutRetry() async {
        MockURLProtocol.handler = { _ in
            (HTTPURLResponse(url: URL(string: "https://gateway.example.com")!, statusCode: 429,
                             httpVersion: nil, headerFields: nil)!,
             Data("{\"detail\":\"rate limited\"}".utf8))
        }
        do {
            _ = try await client.chat(prompt: "x")
            XCTFail("expected ApiError")
        } catch let error as ApiError {
            XCTAssertEqual(error.statusCode, 429)
            XCTAssertEqual(error.detail, "rate limited")
        }
    }

    func testChatParsesInputBlocked() async throws {
        MockURLProtocol.handler = { _ in
            self.json("""
                {"request_id":"req-3","response":null,"status":"input_blocked",
                 "input_guard":{"passed":false,"check":"PII","reason":"SSN detected","reason_code":"pii_detected","risk_score":0.9},
                 "output_guard":null,"latency_ms":5,"model":"—","backend":"—","tokens_remaining":null}
                """)
        }
        let result = try await client.chat(prompt: "my ssn is 123-45-6789")
        XCTAssertEqual(result.status, "input_blocked")
        XCTAssertNil(result.response)
        XCTAssertFalse(result.inputGuard.passed)
        XCTAssertEqual(result.inputGuard.reasonCode, "pii_detected")
        XCTAssertNil(result.outputGuard)
    }

    // MARK: - Streaming

    func testChatStreamYieldsTokensThenDone() async throws {
        MockURLProtocol.handler = { _ in
            self.sse([
                #"{"type":"token","content":"Hel"}"#,
                #"{"type":"token","content":"lo"}"#,
                #"{"type":"done","request_id":"r1","status":"delivered","model":"gpt-test","backend":"openai","latency_ms":100,"input_guard":{"passed":true,"check":"Input","reason":"","reason_code":null,"risk_score":0.0},"output_guard":{"passed":true,"check":"Output","reason":"","reason_code":null,"risk_score":0.0}}"#,
            ])
        }
        var events: [StreamEvent] = []
        for try await event in try await client.chatStream(prompt: "stream") {
            events.append(event)
        }
        XCTAssertEqual(events.count, 3)
        guard case .token(let first) = events[0] else { return XCTFail("expected token") }
        XCTAssertEqual(first, "Hel")
        guard case .done(let status, _, _, let latency, _, _) = events[2] else { return XCTFail("expected done") }
        XCTAssertEqual(status, "delivered")
        XCTAssertEqual(latency, 100)
    }

    func testChatStreamYieldsBlockedEvent() async throws {
        MockURLProtocol.handler = { _ in
            self.sse([
                #"{"type":"blocked","request_id":"r2","status":"input_blocked","input_guard":{"passed":false,"check":"PII","reason":"SSN detected","reason_code":"pii_detected","risk_score":0.9}}"#,
            ])
        }
        var events: [StreamEvent] = []
        for try await event in try await client.chatStream(prompt: "block me") {
            events.append(event)
        }
        XCTAssertEqual(events.count, 1)
        guard case .blocked(let status, let inputGuard, _) = events[0] else { return XCTFail("expected blocked") }
        XCTAssertEqual(status, "input_blocked")
        XCTAssertEqual(inputGuard?.reasonCode, "pii_detected")
        XCTAssertEqual(inputGuard?.riskScore, 0.9)
    }
}