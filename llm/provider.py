"""Configurable LLM provider layer (CLAUDE.md sections 6 and 26).

The provider used for agent reasoning is selected via the LLM_PROVIDER
environment variable so the implementation is never hard-coded to a single
vendor. This capstone runs with the default "deterministic" provider so the
whole workflow is reproducible offline with zero external calls and zero
cost. An "anthropic" provider is stubbed in so a real key could be wired in
later without changing any agent code -- agents only ever call
`get_llm_provider().reason(...)`.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    tokens_used: int | None = None


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def reason(self, task: str, context: dict, instructions: str) -> LLMResponse:
        """Produce a short natural-language explanation for `task` given `context`.

        Implementations must never invent facts not present in `context` --
        this is the same evidence guardrail applied at the LLM layer.
        """


class DeterministicLLMProvider(LLMProvider):
    """Default, fully offline provider.

    Produces templated, evidence-grounded natural language instead of calling
    an external model. This keeps the prototype runnable with no API key
    while still exercising a real "reasoning" seam that could be swapped for
    a live model.
    """

    name = "deterministic"

    def reason(self, task: str, context: dict, instructions: str) -> LLMResponse:
        summary_bits = []
        for key, value in context.items():
            if value in (None, "", [], {}):
                continue
            summary_bits.append(f"{key.replace('_', ' ')}={value}")
        grounded = "; ".join(summary_bits) if summary_bits else "no supporting context provided"
        text = f"[{task}] Based on available evidence ({grounded}). {instructions}".strip()
        return LLMResponse(text=text, provider=self.name, model="deterministic-template-v1")


class AnthropicLLMProvider(LLMProvider):
    """Stub for a live Anthropic-backed provider.

    Not used by default. Requires ANTHROPIC_API_KEY to be set. Kept minimal
    and isolated so no agent code needs to change to enable it -- only the
    LLM_PROVIDER env var.
    """

    name = "anthropic"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY to be set in the environment/.env"
            )

    def reason(self, task: str, context: dict, instructions: str) -> LLMResponse:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "The 'anthropic' package is required for LLM_PROVIDER=anthropic"
            ) from exc

        client = anthropic.Anthropic(api_key=self.api_key)
        prompt = f"Task: {task}\nContext: {context}\nInstructions: {instructions}"
        message = client.messages.create(
            model=self.model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in message.content if hasattr(block, "text"))
        tokens = getattr(message.usage, "output_tokens", None)
        return LLMResponse(text=text, provider=self.name, model=self.model, tokens_used=tokens)


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "deterministic": DeterministicLLMProvider,
    "anthropic": AnthropicLLMProvider,
}


def get_llm_provider() -> LLMProvider:
    provider_name = os.getenv("LLM_PROVIDER", "deterministic").strip().lower()
    provider_cls = _PROVIDERS.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider_name}'. Supported: {sorted(_PROVIDERS)}"
        )
    return provider_cls()
