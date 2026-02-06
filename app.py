"""
FastAPI backend for citation rate analysis.

Provides an API endpoint that accepts a URL, queries multiple LLMs (mock),
and returns per-LLM citation analysis results.
"""

import asyncio
import random
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from extract_urls import extract_urls, count_domains, group_urls_by_domain

app = FastAPI(title="Citation Rate Analyzer")


# ---------------------------------------------------------------------------
# Mock LLM responses — replace with real API calls when keys are available
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSES: dict[str, callable] = {}


def _build_mock_response(target_domain: str, citation_probability: float) -> str:
    """Generate a mock LLM response that may or may not cite the target domain."""
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

    # Decide whether to include target domain citation
    if random.random() < citation_probability:
        target_urls = [
            f"https://{target_domain}/article/analysis",
            f"https://{target_domain}/research/findings",
            f"https://{target_domain}/blog/insights",
        ]
        cited = random.sample(target_urls, k=random.randint(1, 2))
        sources_used.extend(cited)
        response_parts.append(
            f"As reported by {target_domain}, the data shows clear patterns."
        )

    random.shuffle(sources_used)
    source_text = "\n".join(f"- {url}" for url in sources_used)
    body = " ".join(response_parts)
    return f"{body}\n\nSources:\n{source_text}"


LLM_PROFILES = {
    "ChatGPT": {"citation_prob": 0.55, "delay": (0.8, 1.5)},
    "Perplexity": {"citation_prob": 0.80, "delay": (0.6, 1.2)},
    "Claude": {"citation_prob": 0.45, "delay": (0.7, 1.4)},
    "Gemini": {"citation_prob": 0.50, "delay": (0.9, 1.6)},
    "Copilot": {"citation_prob": 0.40, "delay": (0.8, 1.3)},
}


async def query_mock_llm(
    llm_name: str, target_domain: str, num_queries: int = 10
) -> dict:
    """Simulate querying an LLM multiple times and analyzing citation rates."""
    profile = LLM_PROFILES[llm_name]
    delay = random.uniform(*profile["delay"])
    await asyncio.sleep(delay)

    total_citations = 0
    all_urls: list[str] = []
    domain_citation_counts: list[bool] = []

    for _ in range(num_queries):
        response = _build_mock_response(target_domain, profile["citation_prob"])
        urls = extract_urls(response)
        all_urls.extend(urls)

        cited = any(target_domain in url for url in urls)
        domain_citation_counts.append(cited)
        if cited:
            total_citations += 1

    domain_counts = dict(count_domains(all_urls))
    citation_rate = (total_citations / num_queries) * 100

    return {
        "llm": llm_name,
        "total_queries": num_queries,
        "cited_count": total_citations,
        "citation_rate": round(citation_rate, 1),
        "top_domains": dict(
            sorted(domain_counts.items(), key=lambda x: -x[1])[:10]
        ),
        "target_domain_urls": [u for u in all_urls if target_domain in u],
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    url: str
    num_queries: int = 10


@app.post("/api/analyze")
async def analyze_citation(req: AnalyzeRequest):
    """Run citation analysis across all LLMs for the given URL."""
    from urllib.parse import urlparse

    parsed = urlparse(req.url if "://" in req.url else f"https://{req.url}")
    target_domain = parsed.netloc or parsed.path.split("/")[0]

    # Query all LLMs concurrently
    tasks = [
        query_mock_llm(name, target_domain, req.num_queries)
        for name in LLM_PROFILES
    ]
    results = await asyncio.gather(*tasks)

    return {
        "target_url": req.url,
        "target_domain": target_domain,
        "results": sorted(results, key=lambda r: -r["citation_rate"]),
    }


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
