"""
Per-backend LLM circuit breaker.

Protects chat availability when a provider starts failing repeatedly:

  closed    — normal operation; failures are counted inside a rolling window
  open      — calls are rejected immediately for ``cooldown_s`` (CircuitOpenError)
  half-open — after the cooldown, a single probe call is allowed; success
              recloses the breaker, failure reopens it

Use the module-level helpers — they keep a breaker per backend name, so a
failing Groq endpoint never takes down the OpenAI path.
"""
from __future__ import annotations

import time

import httpx


class CircuitOpenError(RuntimeError):
    """Raised when the breaker is open and the backend is temporarily unavailable."""

    def __init__(self, backend: str):
        super().__init__(f"LLM backend '{backend}' is temporarily unavailable (circuit open)")
        self.backend = backend


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_s: float = 30.0,
        window_s: float = 60.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_s = cooldown_s
        self.window_s = window_s

        self._state = "closed"
        self._failures: list[float] = []
        self._opened_at = 0.0
        self._probe_in_flight = False

    @property
    def state(self) -> str:
        """Lazily transition open → half-open once the cooldown has elapsed."""
        if self._state == "open" and time.monotonic() - self._opened_at >= self.cooldown_s:
            self._state = "half_open"
            self._probe_in_flight = False
        return self._state

    def _prune(self) -> None:
        cutoff = time.monotonic() - self.window_s
        self._failures = [t for t in self._failures if t > cutoff]

    def before_call(self) -> None:
        """Raise CircuitOpenError when the breaker will not accept another call."""
        state = self.state
        if state not in ("closed", "half_open"):
            raise CircuitOpenError(self.name)
        if state == "half_open":
            if self._probe_in_flight:
                raise CircuitOpenError(self.name)
            self._probe_in_flight = True

    def on_success(self) -> None:
        if self._state == "half_open":
            self._state = "closed"
            self._failures = []
            self._probe_in_flight = False
            return
        self._prune()

    def on_failure(self) -> None:
        if self._state == "half_open":
            self._state = "open"
            self._opened_at = time.monotonic()
            self._probe_in_flight = False
            return
        self._prune()
        self._failures.append(time.monotonic())
        if len(self._failures) >= self.failure_threshold:
            self._state = "open"
            self._opened_at = time.monotonic()
            self._failures = []

    def reset(self) -> None:
        """Force closed (used by tests and admin ops)."""
        self._state = "closed"
        self._failures = []
        self._opened_at = 0.0
        self._probe_in_flight = False


_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(backend: str) -> CircuitBreaker:
    breaker = _breakers.get(backend)
    if breaker is None:
        breaker = _breakers[backend] = CircuitBreaker(backend)
    return breaker


def is_failure(exc: BaseException) -> bool:
    """True when a backend exception is the kind worth tripping the breaker on.

    Timeouts always count; only 5xx HTTP statuses count (4xx are client-side
    mistakes, not provider outages).
    """
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


def breaker_before(backend: str) -> None:
    get_breaker(backend).before_call()


def breaker_success(backend: str) -> None:
    get_breaker(backend).on_success()


def breaker_failure(backend: str) -> None:
    get_breaker(backend).on_failure()