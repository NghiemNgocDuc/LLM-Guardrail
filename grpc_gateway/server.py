"""
Thin gRPC front for the input guardrail.

Runs the SAME InputGuardrail class (and the SAME default policy rules that
/chat uses when no org policy is configured) as the REST gateway, so a
verdict over gRPC is byte-for-byte the input-gate half of a /chat call.

Deliberately stateless: no database, no rate limits, no LLM call — it is
the guardrail engine exposed on its own port so high-throughput services
can batch prompts over one connection.
"""
import uuid
from concurrent import futures

import grpc

from app.routers.chat import _DEFAULT_INPUT_RULES
from guardrails.input import InputGuardrail

from . import chat_guardrail_pb2, chat_guardrail_pb2_grpc


class GuardrailService(chat_guardrail_pb2_grpc.GuardrailServiceServicer):
    def __init__(self) -> None:
        self._guard = InputGuardrail(_DEFAULT_INPUT_RULES)

    def Check(self, request, context) -> chat_guardrail_pb2.CheckResponse:
        return self._check(request)

    def CheckStream(self, request_iterator, context):
        for request in request_iterator:
            yield self._check(request)

    def _check(self, request: chat_guardrail_pb2.CheckRequest) -> chat_guardrail_pb2.CheckResponse:
        result = self._guard.check(request.prompt)
        return chat_guardrail_pb2.CheckResponse(
            request_id=request.request_id or str(uuid.uuid4()),
            allowed=result.allowed,
            status="delivered" if result.allowed else "input_blocked",
            check=result.check,
            reason=result.reason or "",
            reason_code=result.reason_code,
            risk_score=result.risk_score,
        )


def serve(port: int = 50051) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    chat_guardrail_pb2_grpc.add_GuardrailServiceServicer_to_server(GuardrailService(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server


if __name__ == "__main__":
    server = serve()
    print(f"guardrail gRPC listening on [::]:50051", flush=True)
    server.wait_for_termination()