"""Language model abstraction.

One-method Protocol so any backend (Gemini, Ollama, local model) is pluggable
by implementing a single method. Composer and Validator receive a LanguageModel
by injection — they never import a concrete provider.

SemanticVerdict: the three possible outcomes from a Layer-3 entailment check.
StubLanguageModel: deterministic fake for tests and demo. Returns responses in
sequence, cycling if more calls are made than responses supplied.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol, runtime_checkable


@runtime_checkable
class LanguageModel(Protocol):
    """Minimal interface for any language model backend."""

    def complete(self, prompt: str) -> str: ...


class StubLanguageModel:
    """Deterministic stub: returns responses in sequence, cycling if needed.

    Not thread-safe by design — use one instance per test, never shared state.
    """

    def __init__(self, responses: Sequence[str]) -> None:
        self._responses = list(responses)
        self._idx = 0

    def complete(self, prompt: str) -> str:  # noqa: ARG002
        if not self._responses:
            return ""
        resp = self._responses[self._idx % len(self._responses)]
        self._idx += 1
        return resp

    @property
    def call_count(self) -> int:
        return self._idx


class SemanticVerdict(StrEnum):
    ENTAILED = "entailed"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
