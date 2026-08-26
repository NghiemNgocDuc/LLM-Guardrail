package com.llmguardrails.sdk

import com.sun.net.httpserver.HttpExchange
import com.sun.net.httpserver.HttpServer
import java.io.IOException
import java.net.InetSocketAddress
import java.util.concurrent.atomic.AtomicInteger

/**
 * Self-contained SDK test: a mock gateway (JDK HttpServer) exercises the
 * client end-to-end — auth header, non-streaming parse, 429 retry with
 * Retry-After, blocked responses, SSE token/done/blocked events.
 *
 * Run with:
 *   kotlinc src/main/kotlin/com/llmguardrails/sdk/GuardrailClient.kt test/TestMain.kt -d build/out
 *   java -cp build/out kotlin-stdlib.jar com.llmguardrails.sdk.TestMainKt
 */
object TestMain {
    private var failures = 0
    private val apiKeyHeader = AtomicInteger()

    @JvmStatic
    fun main(args: Array<String>) {
        val server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        var chatCalls = 0
        val port = server.address.port

        server.createContext("/chat") { ex ->
            if (ex.requestHeaders.getFirst("X-Api-Key") != "test-key-123") {
                respond(ex, 401, """{"detail":"missing api key"}""")
                return@createContext
            }
            apiKeyHeader.incrementAndGet()
            val body = ex.requestBody.readBytes().toString(Charsets.UTF_8)
            if (body.contains("no retry")) {
                respond(ex, 429, """{"detail":"rate limited"}""", "Retry-After: 0")
                return@createContext
            }
            chatCalls++
            if (chatCalls == 1) {
                respond(ex, 429, """{"detail":"rate limited"}""", "Retry-After: 0")
                return@createContext
            }
            respond(ex, 200, """
                {
                  "request_id": "req-abc",
                  "response": "Hello from the mock gateway",
                  "status": "delivered",
                  "input_guard": {
                    "passed": true, "check": "Input Checks",
                    "reason": "", "reason_code": null, "risk_score": 0.0
                  },
                  "output_guard": {
                    "passed": true, "check": "Output Checks",
                    "reason": "", "reason_code": null, "risk_score": 0.0
                  },
                  "latency_ms": 42, "model": "gpt-test", "backend": "openai",
                  "tokens_remaining": 999
                }
            """.trimIndent())
        }

        server.createContext("/chat/stream") { ex ->
            if (ex.requestHeaders.getFirst("X-Api-Key") != "test-key-123") {
                respond(ex, 401, """{"detail":"missing api key"}""")
                return@createContext
            }
            val body = ex.requestBody.readBytes().toString(Charsets.UTF_8)
            val blocked = body.contains("block me")
            ex.responseHeaders.add("Content-Type", "text/event-stream")
            ex.sendResponseHeaders(200, 0)
            val out = ex.responseBody
            if (blocked) {
                out.write("data: {\"type\":\"blocked\",\"request_id\":\"r1\",\"status\":\"input_blocked\",\"input_guard\":{\"passed\":false,\"check\":\"PII\",\"reason\":\"SSN detected\",\"reason_code\":\"pii_detected\",\"risk_score\":0.9}}\n\n".toByteArray())
            } else {
                out.write("data: {\"type\":\"token\",\"content\":\"Hel\"}\n\n".toByteArray())
                out.write("data: {\"type\":\"token\",\"content\":\"lo\"}\n\n".toByteArray())
                out.write("data: {\"type\":\"done\",\"request_id\":\"r1\",\"status\":\"delivered\",\"model\":\"gpt-test\",\"backend\":\"openai\",\"latency_ms\":100,\"input_guard\":{\"passed\":true,\"check\":\"Input\",\"reason\":\"\",\"reason_code\":null,\"risk_score\":0.0},\"output_guard\":{\"passed\":true,\"check\":\"Output\",\"reason\":\"\",\"reason_code\":null,\"risk_score\":0.0}}\n\n".toByteArray())
            }
            out.close()
        }

        server.start()
        try {
            val client = GuardrailClient("http://127.0.0.1:$port", "test-key-123", withRetry = true, maxRetries = 2)

            // 1. Non-streaming chat with retry on 429 (Retry-After honored).
            val chat = client.chat("what is the capital of france", temperature = 0.2, maxTokens = 64)
            check(chat.status == "delivered", "chat status")
            check(chat.response == "Hello from the mock gateway", "chat response")
            check(chat.requestId == "req-abc", "chat request_id")
            check(chat.latencyMs == 42L, "chat latency")
            check(chat.model == "gpt-test" && chat.backend == "openai", "chat model/backend")
            check(chat.tokensRemaining == 999L, "chat tokens_remaining")
            check(chat.inputGuard.passed && chat.outputGuard!!.passed, "chat guards passed")
            check(chatCalls == 2, "retry happened (expected 2 calls, got $chatCalls)")
            check(apiKeyHeader.get() >= 2, "X-Api-Key sent on every call")

            // 2. No-retry client surfaces 429 as ApiException.
            val noRetry = GuardrailClient("http://127.0.0.1:$port", "test-key-123")
            try {
                noRetry.chat("no retry")
                check(false, "expected ApiException for 429 without retry")
            } catch (e: ApiException) {
                check(e.statusCode == 429, "429 status code")
            }

            // 3. SSE stream: tokens then done.
            val events = client.chatStream("stream this", maxTokens = 16).toList()
            check(events.size == 3, "expected 3 stream events, got ${events.size}")
            check(events[0] == StreamEvent.Token("Hel"), "first token")
            check(events[1] == StreamEvent.Token("lo"), "second token")
            val done = events[2] as StreamEvent.Done
            check(done.status == "delivered" && done.model == "gpt-test", "done event fields")
            check(done.latencyMs == 100L, "done latency")

            // 4. Blocked stream event.
            val blockedEvents = client.chatStream("please block me now").toList()
            check(blockedEvents.size == 1, "expected 1 blocked event")
            val blocked = blockedEvents[0] as StreamEvent.Blocked
            check(blocked.status == "input_blocked", "blocked status")
            check(blocked.inputGuard!!.reasonCode == "pii_detected", "blocked reason_code")
            check(!blocked.inputGuard.passed && blocked.inputGuard.riskScore == 0.9, "blocked guard fields")

            // 5. JSON core: escaping + parse round trip.
            val round = Json.stringify(mapOf("a" to "quote\"newline\n", "b" to listOf(1, 2.5, true, null)))
            val parsed = Json.parse(round) as Map<*, *>
            check(parsed["a"] == "quote\"newline\n", "JSON escape round trip")
            check((parsed["b"] as List<*>)[1] == 2.5, "JSON number round trip")

            println("ALL KOTLIN SDK TESTS PASSED")
        } catch (e: Throwable) {
            failures++
            e.printStackTrace()
            println("KOTLIN SDK TESTS FAILED: ${e.message}")
        } finally {
            server.stop(0)
        }
        if (failures > 0) throw RuntimeException("test failures")
    }

    private fun respond(ex: HttpExchange, code: Int, body: String, vararg headers: String) {
        for (h in headers) {
            val (k, v) = h.split(":", limit = 2)
            ex.responseHeaders.add(k.trim(), v.trim())
        }
        val bytes = body.toByteArray()
        ex.sendResponseHeaders(code, bytes.size.toLong())
        try {
            ex.responseBody.write(bytes)
        } finally {
            ex.close()
        }
    }

    private fun check(cond: Boolean, label: String) {
        if (!cond) throw IOException("ASSERT FAILED: $label")
    }
}