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

from extract_urls import (
    extract_urls,
    count_domains,
    group_urls_by_domain,
    extract_brand_mentions,
    analyze_sentiment,
    analyze_position,
)
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
        "response_text": resp.text,
    }


async def analyze_llm(
    client: BaseLLMClient,
    target_domain: str,
    brand: str,
    num_queries: int,
    custom_prompts: list[str] | None = None,
    competitors: list[str] | None = None,
) -> dict:
    """Run multiple queries against one LLM and aggregate citation stats."""
    if custom_prompts:
        queries = custom_prompts
        num_queries = len(queries)
    else:
        queries = generate_queries(target_domain, brand, num_queries)

    is_mock = isinstance(client, MockLLMClient)

    if is_mock:
        tasks = [run_single_query(client, q, target_domain) for q in queries]
        results = await asyncio.gather(*tasks)
    else:
        results = []
        for q in queries:
            r = await run_single_query(client, q, target_domain)
            results.append(r)
            await asyncio.sleep(4)

    cited_count = 0
    mentioned_count = 0
    all_urls: list[str] = []
    errors = 0
    query_details: list[dict] = []
    sentiments: list[dict] = []
    positions: list[dict] = []
    competitor_citations: dict[str, int] = {c: 0 for c in (competitors or [])}

    for r in results:
        resp_text = r.get("response_text", "") or r.get("response", "")
        urls = r.get("urls", [])

        # Sentiment analysis
        sent = analyze_sentiment(resp_text, brand)
        sentiments.append(sent)

        # Position analysis
        pos = analyze_position(resp_text, target_domain, brand)
        positions.append(pos)

        # Brand mention (text, not URL)
        brand_mentioned = brand.lower() in resp_text.lower()
        if brand_mentioned:
            mentioned_count += 1

        # Competitor citation check
        for comp in (competitors or []):
            comp_domain = comp.lower().replace("www.", "")
            if any(comp_domain in u.lower() for u in urls) or comp.lower() in resp_text.lower():
                competitor_citations[comp] += 1

        detail = {
            "query": r.get("query", ""),
            "response": r.get("response", ""),
            "cited": r.get("cited", False),
            "urls": urls,
            "error": r.get("error"),
            "sentiment": sent,
            "position": pos,
            "brand_mentioned": brand_mentioned,
        }
        query_details.append(detail)

        if r.get("error"):
            errors += 1
            continue
        all_urls.extend(urls)
        if r["cited"]:
            cited_count += 1

    successful = num_queries - errors
    citation_rate = (cited_count / successful * 100) if successful > 0 else 0
    mention_rate = (mentioned_count / successful * 100) if successful > 0 else 0
    domain_counts = dict(count_domains(all_urls))

    # Aggregate sentiment
    valid_sentiments = [s for s in sentiments if s["label"] != "neutral" or s["positive"] + s["negative"] > 0]
    avg_sentiment = round(
        sum(s["score"] for s in sentiments) / len(sentiments), 2
    ) if sentiments else 0
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    for s in sentiments:
        sentiment_dist[s["label"]] += 1

    # Aggregate position
    valid_positions = [p for p in positions if p["section"] != "none"]
    avg_position = round(
        sum(p["position_pct"] for p in valid_positions) / len(valid_positions), 1
    ) if valid_positions else -1
    position_dist = {"top": 0, "middle": 0, "bottom": 0, "none": 0}
    for p in positions:
        position_dist[p["section"]] += 1

    # Competitor rates
    comp_rates = {}
    for comp, count in competitor_citations.items():
        comp_rates[comp] = round((count / successful * 100), 1) if successful > 0 else 0

    is_mock = isinstance(client, MockLLMClient)

    return {
        "llm": client.name,
        "mode": "mock" if is_mock else "live",
        "total_queries": num_queries,
        "successful_queries": successful,
        "errors": errors,
        "cited_count": cited_count,
        "citation_rate": round(citation_rate, 1),
        "mention_rate": round(mention_rate, 1),
        "avg_sentiment": avg_sentiment,
        "sentiment_dist": sentiment_dist,
        "avg_position": avg_position,
        "position_dist": position_dist,
        "competitor_rates": comp_rates,
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
    competitors: list[str] | None = None


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
        analyze_llm(c, target_domain, brand, req.num_queries, req.custom_prompts, req.competitors)
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
