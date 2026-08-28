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


class ClaudeLanguageModel:
    """Anthropic Claude backend for the Composer and Validator."""

    def __init__(
        self, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 2048
    ) -> None:
        import anthropic  # noqa: PLC0415 — deferred so anthropic is optional

        self._client = anthropic.Anthropic()
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, prompt: str) -> str:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        block = message.content[0]
        return block.text if hasattr(block, "text") else str(block)


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
