package com.llmguardrails.sdk

import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.net.http.HttpTimeoutException
import java.time.Duration

/**
 * Minimal JSON core (parse + escape) so the SDK has zero third-party
 * dependencies and runs on plain JVM/Android toolchains.
 */
internal object Json {
    fun parse(text: String): Any? {
        val p = Parser(text)
        val v = p.parseValue()
        p.skipWs()
        if (!p.atEnd()) throw IllegalArgumentException("trailing JSON content")
        return v
    }

    fun stringify(value: Any?): String = buildString { write(this, value) }

    fun write(b: StringBuilder, value: Any?) {
        when (value) {
            null -> b.append("null")
            is String -> { b.append('"'); escape(b, value); b.append('"') }
            is Boolean -> b.append(if (value) "true" else "false")
            is Number -> b.append(value.toString())
            is Map<*, *> -> {
                b.append('{')
                var first = true
                for ((k, v) in value) {
                    if (!first) b.append(',')
                    first = false
                    write(b, k.toString()); b.append(':'); write(b, v)
                }
                b.append('}')
            }
            is List<*> -> {
                b.append('[')
                var first = true
                for (v in value) {
                    if (!first) b.append(',')
                    first = false
                    write(b, v)
                }
                b.append(']')
            }
            else -> throw IllegalArgumentException("unsupported JSON value: $value")
        }
    }

    private fun escape(b: StringBuilder, s: String) {
        for (c in s) when (c) {
            '"' -> b.append("\\\"")
            '\\' -> b.append("\\\\")
            '\n' -> b.append("\\n")
            '\r' -> b.append("\\r")
            '\t' -> b.append("\\t")
            '\u0008' -> b.append("\\b")
            '\u000C' -> b.append("\\f")
            else -> if (c < ' ') b.append("\\u%04x".format(c.code)) else b.append(c)
        }
    }

    private class Parser(val s: String) {
        var i = 0
        fun atEnd() = i >= s.length
        fun skipWs() { while (i < s.length && s[i].isWhitespace()) i++ }

        fun parseValue(): Any? {
            skipWs()
            if (atEnd()) throw IllegalArgumentException("unexpected end of JSON")
            return when (s[i]) {
                '{' -> parseObject()
                '[' -> parseArray()
                '"' -> parseString()
                't' -> { expect("true"); true }
                'f' -> { expect("false"); false }
                'n' -> { expect("null"); null }
                else -> parseNumber()
            }
        }

        private fun expect(word: String) {
            if (!s.startsWith(word, i)) throw IllegalArgumentException("invalid JSON literal")
            i += word.length
        }

        private fun parseObject(): Map<String, Any?> {
            i++ // '{'
            val out = LinkedHashMap<String, Any?>()
            skipWs()
            if (i < s.length && s[i] == '}') { i++; return out }
            while (true) {
                skipWs()
                if (i >= s.length || s[i] != '"') throw IllegalArgumentException("expected string key")
                val key = parseString()
                skipWs()
                if (i >= s.length || s[i] != ':') throw IllegalArgumentException("expected ':'")
                i++
                out[key] = parseValue()
                skipWs()
                if (i >= s.length) throw IllegalArgumentException("unterminated object")
                when (s[i]) {
                    ',' -> i++
                    '}' -> { i++; return out }
                    else -> throw IllegalArgumentException("expected ',' or '}'")
                }
            }
        }

        private fun parseArray(): List<Any?> {
            i++ // '['
            val out = ArrayList<Any?>()
            skipWs()
            if (i < s.length && s[i] == ']') { i++; return out }
            while (true) {
                out.add(parseValue())
                skipWs()
                if (i >= s.length) throw IllegalArgumentException("unterminated array")
                when (s[i]) {
                    ',' -> i++
                    ']' -> { i++; return out }
                    else -> throw IllegalArgumentException("expected ',' or ']'")
                }
            }
        }

        private fun parseString(): String {
            i++ // '"'
            val out = StringBuilder()
            while (true) {
                if (i >= s.length) throw IllegalArgumentException("unterminated string")
                when (val c = s[i]) {
                    '"' -> { i++; return out.toString() }
                    '\\' -> {
                        i++
                        if (i >= s.length) throw IllegalArgumentException("bad escape")
                        when (val e = s[i]) {
                            '"' -> out.append('"')
                            '\\' -> out.append('\\')
                            '/' -> out.append('/')
                            'b' -> out.append('\u0008')
                            'f' -> out.append('\u000C')
                            'n' -> out.append('\n')
                            'r' -> out.append('\r')
                            't' -> out.append('\t')
                            'u' -> {
                                if (i + 4 >= s.length) throw IllegalArgumentException("bad unicode escape")
                                out.append(s.substring(i + 1, i + 5).toInt(16).toChar())
                                i += 4
                            }
                            else -> throw IllegalArgumentException("bad escape \\$e")
                        }
                        i++
                    }
                    else -> { out.append(c); i++ }
                }
            }
        }

        private fun parseNumber(): Number {
            val start = i
            if (i < s.length && s[i] == '-') i++
            while (i < s.length && s[i].isDigit()) i++
            if (i < s.length && s[i] == '.') {
                i++
                while (i < s.length && s[i].isDigit()) i++
            }
            if (i < s.length && (s[i] == 'e' || s[i] == 'E')) {
                i++
                if (i < s.length && (s[i] == '+' || s[i] == '-')) i++
                while (i < s.length && s[i].isDigit()) i++
            }
            val text = s.substring(start, i)
            return text.toDoubleOrNull()?.let { if (it % 1.0 == 0.0 && !text.contains('.')) it.toLong() else it }
                ?: throw IllegalArgumentException("invalid number '$text'")
        }
    }
}

/** Mirrors GuardrailResult from the gateway OpenAPI schema. */
data class GuardrailResult(
    val passed: Boolean,
    val check: String,
    val reason: String,
    val reasonCode: String,
    val riskScore: Double,
)

/** Mirrors ChatResponse from the gateway OpenAPI schema. */
data class ChatResponse(
    val requestId: String,
    val response: String?,
    val status: String,
    val inputGuard: GuardrailResult,
    val outputGuard: GuardrailResult?,
    val latencyMs: Long,
    val model: String,
    val backend: String,
    val tokensRemaining: Long?,
)

/** SSE events from /chat/stream — mirrors the JS/Python SDKs. */
sealed class StreamEvent {
    data class Token(val content: String) : StreamEvent()
    data class Done(
        val status: String,
        val model: String,
        val backend: String,
        val latencyMs: Long,
        val inputGuard: GuardrailResult,
        val outputGuard: GuardrailResult?,
    ) : StreamEvent()
    data class Blocked(
        val status: String,
        val inputGuard: GuardrailResult?,
        val outputGuard: GuardrailResult?,
    ) : StreamEvent()
    data class Error(val detail: String) : StreamEvent()
    object Ping : StreamEvent()
}

/** HTTP error carrying the gateway's JSON `detail` when available. */
class ApiException(
    val statusCode: Int,
    val detail: String,
) : RuntimeException("HTTP $statusCode: $detail")

/**
 * Client for the LLM Guardrails gateway — API-identical to
 * sdk/javascript/guardrailClient.mjs and sdk/python/guardrail_client.py.
 *
 * Auth is the `X-Api-Key` header (the same key the gateway issues to
 * servers). See README.md — do NOT ship a gateway key inside a mobile app.
 */
class GuardrailClient(
    private val baseUrl: String,
    private val apiKey: String,
    private val timeoutSeconds: Long = 30,
    private val withRetry: Boolean = false,
    private val maxRetries: Int = 3,
) {
    private val http: HttpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(timeoutSeconds))
        .build()

    private val endpointBase: String = baseUrl.trimEnd('/')

    /** Non-streaming chat. Throws [ApiException] for non-2xx responses. */
    fun chat(
        prompt: String,
        model: String? = null,
        backend: String? = null,
        temperature: Double = 0.7,
        maxTokens: Int = 256,
    ): ChatResponse {
        val body = payload(prompt, model, backend, temperature, maxTokens)
        val retries = if (withRetry) maxRetries else 0
        for (attempt in 1..retries + 1) {
            val response = send("POST", "$endpointBase/chat", body)
            if ((response.statusCode() == 402 || response.statusCode() == 429) && attempt <= retries) {
                Thread.sleep(retryDelay(response, attempt))
                continue
            }
            return parseChat(response)
        }
        throw IllegalStateException("unreachable")
    }

    /**
     * SSE stream from /chat/stream. Blocking (no coroutine dependency);
     * yields [StreamEvent] objects as the stream progresses. Retries only
     * happen before the first event arrives.
     */
    fun chatStream(
        prompt: String,
        model: String? = null,
        backend: String? = null,
        temperature: Double = 0.7,
        maxTokens: Int = 256,
    ): Sequence<StreamEvent> {
        val body = payload(prompt, model, backend, temperature, maxTokens)
        val retries = if (withRetry) maxRetries else 0
        var attempt = 0
        var firstEvent = true
        return sequence {
            while (true) {
                attempt++
                val request = buildRequest("POST", "$endpointBase/chat/stream", body)
                val response = http.send(request, HttpResponse.BodyHandlers.ofLines())
                if ((response.statusCode() == 402 || response.statusCode() == 429) && attempt <= retries && firstEvent) {
                    Thread.sleep(retryDelay(response, attempt))
                    continue
                }
                if (response.statusCode() !in 200..299) {
                    throw parseError(response.statusCode(), response.body().toList().joinToString("\n"))
                }
                for (line in response.body()) {
                    if (line.startsWith("data: ")) {
                        firstEvent = false
                        yield(parseEvent(line.substring(6)))
                    }
                }
                break
            }
        }
    }

    private fun payload(
        prompt: String,
        model: String?,
        backend: String?,
        temperature: Double,
        maxTokens: Int,
    ): Map<String, Any?> {
        val out = LinkedHashMap<String, Any?>()
        out["prompt"] = prompt
        out["temperature"] = temperature
        out["max_tokens"] = maxTokens
        if (!model.isNullOrBlank()) out["model"] = model
        if (!backend.isNullOrBlank()) out["backend"] = backend
        return out
    }

    private fun send(method: String, url: String, body: Map<String, Any?>): HttpResponse<String> {
        val request = buildRequest(method, url, body)
        return try {
            http.send(request, HttpResponse.BodyHandlers.ofString())
        } catch (e: HttpTimeoutException) {
            throw ApiException(0, "request timed out after ${timeoutSeconds}s")
        } catch (e: java.io.IOException) {
            throw ApiException(0, e.message ?: "network error")
        }
    }

    private fun buildRequest(method: String, url: String, body: Map<String, Any?>): HttpRequest {
        val builder = HttpRequest.newBuilder(URI.create(url))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .header("Content-Type", "application/json")
            .header("X-Api-Key", apiKey)
        if (method == "POST") {
            builder.POST(HttpRequest.BodyPublishers.ofString(Json.stringify(body)))
        } else {
            builder.GET()
        }
        return builder.build()
    }

    private fun parseChat(response: HttpResponse<String>): ChatResponse {
        if (response.statusCode() !in 200..299) throw parseError(response.statusCode(), response.body())
        val obj = asObject(Json.parse(response.body()))
        return ChatResponse(
            requestId = str(obj, "request_id") ?: "",
            response = str(obj, "response"),
            status = str(obj, "status") ?: "error",
            inputGuard = guardResult(obj["input_guard"]),
            outputGuard = (obj["output_guard"] as? Map<*, *>)?.let { guardResult(it) },
            latencyMs = num(obj, "latency_ms")?.toLong() ?: 0,
            model = str(obj, "model") ?: "",
            backend = str(obj, "backend") ?: "",
            tokensRemaining = num(obj, "tokens_remaining")?.toLong(),
        )
    }

    private fun parseEvent(json: String): StreamEvent {
        val obj = asObject(Json.parse(json))
        return when (str(obj, "type")) {
            "token" -> StreamEvent.Token(str(obj, "content") ?: "")
            "done" -> StreamEvent.Done(
                status = str(obj, "status") ?: "delivered",
                model = str(obj, "model") ?: "",
                backend = str(obj, "backend") ?: "",
                latencyMs = num(obj, "latency_ms")?.toLong() ?: 0,
                inputGuard = guardResult(obj["input_guard"]),
                outputGuard = (obj["output_guard"] as? Map<*, *>)?.let { guardResult(it) },
            )
            "blocked" -> StreamEvent.Blocked(
                status = str(obj, "status") ?: "blocked",
                inputGuard = (obj["input_guard"] as? Map<*, *>)?.let { guardResult(it) },
                outputGuard = (obj["output_guard"] as? Map<*, *>)?.let { guardResult(it) },
            )
            "error" -> StreamEvent.Error(str(obj, "detail") ?: "unknown error")
            else -> StreamEvent.Ping
        }
    }

    private fun guardResult(value: Any?): GuardrailResult {
        val obj = asObject(value)
        return GuardrailResult(
            passed = obj["passed"] == true,
            check = str(obj, "check") ?: "",
            reason = str(obj, "reason") ?: "",
            reasonCode = str(obj, "reason_code") ?: "",
            riskScore = num(obj, "risk_score") ?: 0.0,
        )
    }

    private fun parseError(statusCode: Int, body: String): ApiException {
        val detail = try {
            val obj = asObject(Json.parse(body))
            str(obj, "detail") ?: body.take(200)
        } catch (_: Exception) {
            body.take(200)
        }
        return ApiException(statusCode, detail)
    }

    private fun retryDelay(response: HttpResponse<*>, attempt: Int): Long {
        val retryAfter = response.headers().firstValue("Retry-After").orElse(null)
        retryAfter?.toLongOrNull()?.let { return it * 1000 }
        return minOf(1L shl (attempt - 1), 8L) * 1000
    }

    @Suppress("UNCHECKED_CAST")
    private fun asObject(value: Any?): Map<String, Any?> =
        value as? Map<String, Any?> ?: throw ApiException(0, "unexpected response shape")

    private fun str(obj: Map<String, Any?>, key: String): String? = obj[key] as? String
    private fun num(obj: Map<String, Any?>, key: String): Double? = (obj[key] as? Number)?.toDouble()
}