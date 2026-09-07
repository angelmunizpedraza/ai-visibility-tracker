"""Answer-engine providers.

Each provider exposes `ask(prompt) -> Answer`. Real providers call the vendor
HTTP API with plain `requests` (no SDK lock-in); `FakeProvider` returns canned
answers and is what the test-suite uses. API keys are read from environment
variables so nothing sensitive ever lands in a config file.

    OPENAI_API_KEY      -> ChatGPTProvider     (gpt-4o-mini by default)
    PERPLEXITY_API_KEY  -> PerplexityProvider  (sonar by default, returns citations)
    ANTHROPIC_API_KEY   -> ClaudeProvider      (claude-3-5-haiku-latest by default)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol

import requests


@dataclass
class Answer:
    provider: str
    model: str
    prompt: str
    text: str
    citations: List[str] = field(default_factory=list)
    latency_ms: int = 0
    raw: Optional[dict] = None


class Provider(Protocol):
    name: str

    def ask(self, prompt: str) -> Answer: ...


class ProviderError(RuntimeError):
    pass


def _require_key(env: str) -> str:
    key = os.environ.get(env)
    if not key:
        raise ProviderError(f"Missing {env} in environment")
    return key


def _post(url: str, headers: dict, payload: dict, timeout: int = 60) -> dict:
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if resp.status_code >= 400:
        raise ProviderError(f"{url} -> HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


class ChatGPTProvider:
    name = "chatgpt"

    def __init__(self, model: str = "gpt-4o-mini", system: str | None = None):
        self.model = model
        self.system = system or (
            "You are a helpful assistant. Answer the user's question directly and, "
            "when you recommend companies, products or websites, name them explicitly "
            "and include their URLs."
        )

    def ask(self, prompt: str) -> Answer:
        key = _require_key("OPENAI_API_KEY")
        t0 = time.time()
        data = _post(
            "https://api.openai.com/v1/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
        )
        text = data["choices"][0]["message"]["content"]
        return Answer(self.name, self.model, prompt, text, [], int((time.time() - t0) * 1000), data)


class PerplexityProvider:
    name = "perplexity"

    def __init__(self, model: str = "sonar"):
        self.model = model

    def ask(self, prompt: str) -> Answer:
        key = _require_key("PERPLEXITY_API_KEY")
        t0 = time.time()
        data = _post(
            "https://api.perplexity.ai/chat/completions",
            {"Authorization": f"Bearer {key}"},
            {"model": self.model, "messages": [{"role": "user", "content": prompt}]},
        )
        text = data["choices"][0]["message"]["content"]
        citations = list(data.get("citations") or [])
        return Answer(self.name, self.model, prompt, text, citations, int((time.time() - t0) * 1000), data)


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str = "claude-3-5-haiku-latest"):
        self.model = model

    def ask(self, prompt: str) -> Answer:
        key = _require_key("ANTHROPIC_API_KEY")
        t0 = time.time()
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {
                "model": self.model,
                "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        text = "".join(block.get("text", "") for block in data.get("content", []))
        return Answer(self.name, self.model, prompt, text, [], int((time.time() - t0) * 1000), data)


class FakeProvider:
    """Deterministic provider for tests and dry runs."""

    name = "fake"

    def __init__(self, answers: Dict[str, str] | None = None, citations: Dict[str, List[str]] | None = None, name: str = "fake"):
        self.name = name
        self.model = "fake-1"
        self._answers = answers or {}
        self._citations = citations or {}
        self.calls: List[str] = []

    def ask(self, prompt: str) -> Answer:
        self.calls.append(prompt)
        return Answer(
            self.name,
            self.model,
            prompt,
            self._answers.get(prompt, ""),
            list(self._citations.get(prompt, [])),
            1,
        )


REGISTRY = {
    "chatgpt": ChatGPTProvider,
    "perplexity": PerplexityProvider,
    "claude": ClaudeProvider,
}


def build_providers(names: List[str]) -> List[Provider]:
    out: List[Provider] = []
    for n in names:
        n = n.strip().lower()
        if n not in REGISTRY:
            raise ProviderError(f"Unknown provider '{n}'. Known: {', '.join(REGISTRY)}")
        out.append(REGISTRY[n]())
    return out
