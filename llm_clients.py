"""
LLM API clients for citation rate analysis.

Each client queries a real LLM API via httpx and returns the response text
plus any structured citations. All API keys are read from environment variables.
"""

import os
import json
import asyncio
import random
import httpx
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Query generation
# ---------------------------------------------------------------------------

QUERY_TEMPLATES = [
    "What are the main products and services offered by {brand}? Provide source URLs.",
    "Tell me about {brand}'s latest news, developments, and innovations. Include references.",
    "What is {domain} and what kind of information can I find on that website? Cite sources.",
    "Compare {brand} with its main competitors. Include source links.",
    "What do industry experts and reviewers say about {brand}? Cite your sources.",
    "Provide a comprehensive overview of {brand}'s history and achievements with references.",
    "What are the top-rated products or services from {brand}? Include URLs to reviews.",
    "How does {brand} rank in its industry? Provide data and source URLs.",
    "What recent announcements has {brand} made? Provide news source links.",
    "Recommend the best resources to learn more about {brand}. Include website URLs.",
    "What is {brand}'s market strategy and competitive advantage? Cite references.",
    "Summarize the latest research or reports published by {brand}. Include links.",
]


def generate_queries(domain: str, brand: str, num: int) -> list[str]:
    """Generate diverse prompts about the target domain/brand."""
    templates = list(QUERY_TEMPLATES)
    random.shuffle(templates)
    queries = []
    for i in range(num):
        tmpl = templates[i % len(templates)]
        queries.append(tmpl.format(domain=domain, brand=brand))
    return queries


def domain_to_brand(domain: str) -> str:
    """Extract a human-readable brand name from a domain.
    e.g. 'www.samsung.com' -> 'Samsung', 'news.naver.com' -> 'Naver'
    """
    parts = domain.lower().replace("www.", "").split(".")
    name = parts[0] if parts else domain
    return name.capitalize()


# ---------------------------------------------------------------------------
# Response data
# ---------------------------------------------------------------------------

@dataclass
class LLMResponse:
    text: str
    citations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

class BaseLLMClient:
    name: str = ""
    env_key: str = ""

    def is_available(self) -> bool:
        return bool(os.getenv(self.env_key))

    async def query(self, prompt: str) -> LLMResponse:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# OpenAI (ChatGPT)
# ---------------------------------------------------------------------------

class OpenAIClient(BaseLLMClient):
    name = "ChatGPT"
    env_key = "OPENAI_API_KEY"

    async def query(self, prompt: str) -> LLMResponse:
        api_key = os.getenv(self.env_key)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a helpful research assistant. "
                                "Always include relevant source URLs in your responses "
                                "when referencing information or making claims."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.7,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return LLMResponse(text=text)


# ---------------------------------------------------------------------------
# Perplexity
# ---------------------------------------------------------------------------

class PerplexityClient(BaseLLMClient):
    name = "Perplexity"
    env_key = "PERPLEXITY_API_KEY"

    async def query(self, prompt: str) -> LLMResponse:
        api_key = os.getenv(self.env_key)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "sonar",
                    "messages": [
                        {
                            "role": "system",
                            "content": "Be precise and cite your sources with URLs.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]

            # Perplexity returns structured citations
            citations = data.get("citations", [])
            return LLMResponse(text=text, citations=citations)


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------

class AnthropicClient(BaseLLMClient):
    name = "Claude"
    env_key = "ANTHROPIC_API_KEY"

    async def query(self, prompt: str) -> LLMResponse:
        api_key = os.getenv(self.env_key)
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                "Please include source URLs when referencing information.\n\n"
                                + prompt
                            ),
                        }
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["content"][0]["text"]
            return LLMResponse(text=text)


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

class GeminiClient(BaseLLMClient):
    name = "Gemini"
    env_key = "GEMINI_API_KEY"

    async def query(self, prompt: str) -> LLMResponse:
        api_key = os.getenv(self.env_key)
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={api_key}"
        )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": (
                                        "Please include source URLs when referencing information.\n\n"
                                        + prompt
                                    )
                                }
                            ]
                        }
                    ],
                    "generationConfig": {"temperature": 0.7},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]

            # Check for grounding metadata citations
            citations = []
            metadata = data["candidates"][0].get("groundingMetadata", {})
            for chunk in metadata.get("groundingChunks", []):
                web = chunk.get("web", {})
                if web.get("uri"):
                    citations.append(web["uri"])

            return LLMResponse(text=text, citations=citations)


# ---------------------------------------------------------------------------
# Mock client (fallback when no API keys)
# ---------------------------------------------------------------------------

class MockLLMClient(BaseLLMClient):
    """Generates fake responses for demo/testing."""

    def __init__(self, name: str, citation_prob: float = 0.5):
        self.name = name
        self._citation_prob = citation_prob

    def is_available(self) -> bool:
        return True  # always available

    async def query(self, prompt: str) -> LLMResponse:
        await asyncio.sleep(random.uniform(0.1, 0.3))

        base_sources = [
            "https://en.wikipedia.org/wiki/relevant_topic",
            "https://www.nature.com/articles/research-paper",
            "https://arxiv.org/abs/2024.12345",
            "https://www.reuters.com/technology/article",
            "https://techcrunch.com/2024/01/news-article",
            "https://scholar.google.com/citations?id=abc",
            "https://www.nytimes.com/2024/science/topic",
            "https://stackoverflow.com/questions/12345",
        ]

        sentences = [
            "According to recent research, this topic has gained significant attention.",
            "Multiple sources confirm the growing trend in this area.",
            "Industry experts have noted substantial developments recently.",
            "Academic literature supports these findings extensively.",
            "Several publications have documented this phenomenon.",
        ]

        response_parts = random.sample(sentences, k=random.randint(3, 5))
        sources_used = random.sample(base_sources, k=random.randint(2, 5))

        return LLMResponse(
            text=" ".join(response_parts) + "\n\nSources:\n" + "\n".join(f"- {u}" for u in sources_used),
            citations=[],
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_REAL_CLIENTS: list[BaseLLMClient] = [
    OpenAIClient(),
    PerplexityClient(),
    AnthropicClient(),
    GeminiClient(),
]

MOCK_PROFILES: dict[str, float] = {
    "ChatGPT": 0.55,
    "Perplexity": 0.80,
    "Claude": 0.45,
    "Gemini": 0.50,
}


def get_active_clients(use_mock_fallback: bool = True) -> list[BaseLLMClient]:
    """Return available real clients, plus mock fallbacks if enabled."""
    real = [c for c in ALL_REAL_CLIENTS if c.is_available()]
    real_names = {c.name for c in real}

    if use_mock_fallback:
        for name, prob in MOCK_PROFILES.items():
            if name not in real_names:
                real.append(MockLLMClient(name=name, citation_prob=prob))

    return real


def get_status() -> dict[str, str]:
    """Return each LLM's connection status: 'live' or 'mock'."""
    status = {}
    for c in ALL_REAL_CLIENTS:
        status[c.name] = "live" if c.is_available() else "mock"
    return status
