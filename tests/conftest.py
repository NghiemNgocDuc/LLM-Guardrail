"""Shared fixtures — engine-mode parametrization for guardrail tests.

`engine_mode` runs each test in a module twice: once with GUARDRAIL_ENGINE=rust
(the compiled PyO3 extension, when installed) and once with GUARDRAIL_ENGINE=python
(the pure-Python fallback). Modules that exercise ported checks opt in with:

    pytestmark = pytest.mark.usefixtures("engine_mode")
"""
import os

import pytest

import guardrails._engine as _engine

_ENGINE_VAR = "GUARDRAIL_ENGINE"


@pytest.fixture(params=["rust", "python"])
def engine_mode(request, monkeypatch):
    monkeypatch.setenv(_ENGINE_VAR, request.param)
    _engine.reset()
    yield request.param
    monkeypatch.delenv(_ENGINE_VAR, raising=False)
    _engine.reset()
