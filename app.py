"""
FastAPI backend for citation rate analysis.

Queries real LLM APIs (ChatGPT, Perplexity, Claude, Gemini) to measure
how often each LLM cites a target URL/domain. Falls back to mock data
when API keys are not configured.
"""

import asyncio
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from extract_urls import extract_urls, count_domains, group_urls_by_domain
from llm_clients import (
    BaseLLMClient,
    MockLLMClient,
    generate_queries,
    domain_to_brand,
    get_active_clients,
    get_status,
)

load_dotenv()

app = FastAPI(title="Citation Rate Analyzer")


# ---------------------------------------------------------------------------
# Core analysis logic
# ---------------------------------------------------------------------------

async def run_single_query(
    client: BaseLLMClient,
    prompt: str,
    target_domain: str,
) -> dict:
    """Run one query against an LLM and check if the target domain is cited."""
    try:
        resp = await client.query(prompt)
    except Exception as e:
        return {"error": str(e), "cited": False, "urls": [], "query": prompt, "response": ""}

    # Combine text-extracted URLs and structured citations
    text_urls = extract_urls(resp.text)
    all_urls = list(set(text_urls + resp.citations))

    cited = any(target_domain in url for url in all_urls)

    # For mock clients: inject target domain with probability
    if isinstance(client, MockLLMClient) and not cited:
        import random
        if random.random() < client._citation_prob:
            fake_url = f"https://{target_domain}/page/{random.randint(1,99)}"
            all_urls.append(fake_url)
            cited = True

    return {
        "cited": cited,
        "urls": all_urls,
        "error": None,
        "query": prompt,
        "response": resp.text,
    }


async def analyze_llm(
    client: BaseLLMClient,
    target_domain: str,
    brand: str,
    num_queries: int,
    custom_prompts: list[str] | None = None,
) -> dict:
    """Run multiple queries against one LLM and aggregate citation stats."""
    if custom_prompts:
        queries = custom_prompts
        num_queries = len(queries)
    else:
        queries = generate_queries(target_domain, brand, num_queries)

    is_mock = isinstance(client, MockLLMClient)

    if is_mock:
        # Mock: fire all at once
        tasks = [run_single_query(client, q, target_domain) for q in queries]
        results = await asyncio.gather(*tasks)
    else:
        # Real API: send sequentially with delay to avoid rate limits
        results = []
        for q in queries:
            r = await run_single_query(client, q, target_domain)
            results.append(r)
            await asyncio.sleep(4)  # 4s gap → max 15 req/min

    cited_count = 0
    all_urls: list[str] = []
    errors = 0
    query_details: list[dict] = []

    for r in results:
        detail = {
            "query": r.get("query", ""),
            "response": r.get("response", ""),
            "cited": r.get("cited", False),
            "urls": r.get("urls", []),
            "error": r.get("error"),
        }
        query_details.append(detail)

        if r.get("error"):
            errors += 1
            continue
        all_urls.extend(r["urls"])
        if r["cited"]:
            cited_count += 1

    successful = num_queries - errors
    citation_rate = (cited_count / successful * 100) if successful > 0 else 0
    domain_counts = dict(count_domains(all_urls))

    is_mock = isinstance(client, MockLLMClient)

    return {
        "llm": client.name,
        "mode": "mock" if is_mock else "live",
        "total_queries": num_queries,
        "successful_queries": successful,
        "errors": errors,
        "cited_count": cited_count,
        "citation_rate": round(citation_rate, 1),
        "top_domains": dict(
            sorted(domain_counts.items(), key=lambda x: -x[1])[:10]
        ),
        "target_domain_urls": [u for u in all_urls if target_domain in u],
        "query_details": query_details,
    }


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    url: str
    num_queries: int = 10
    custom_prompts: list[str] | None = None


@app.get("/api/status")
async def llm_status():
    """Return each LLM's connection status (live / mock)."""
    return get_status()


@app.post("/api/analyze")
async def analyze_citation(req: AnalyzeRequest):
    """Run citation analysis across all available LLMs."""
    parsed = urlparse(req.url if "://" in req.url else f"https://{req.url}")
    target_domain = parsed.netloc or parsed.path.split("/")[0]
    brand = domain_to_brand(target_domain)

    clients = get_active_clients(use_mock_fallback=True)

    tasks = [
        analyze_llm(c, target_domain, brand, req.num_queries, req.custom_prompts)
        for c in clients
    ]
    results = await asyncio.gather(*tasks)

    return {
        "target_url": req.url,
        "target_domain": target_domain,
        "brand": brand,
        "results": sorted(results, key=lambda r: -r["citation_rate"]),
    }


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
