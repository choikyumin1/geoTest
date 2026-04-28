"""
FastAPI backend for AEO (Answer Engine Optimization) analysis.

Queries real LLM APIs (ChatGPT, Perplexity, Claude, Gemini) to measure
citation rate, recommendation rate, sentiment, position, citation depth,
and share of voice. Falls back to mock data when API keys are missing.
"""

import asyncio
import random
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from extract_urls import (
    extract_urls,
    count_domains,
    analyze_sentiment,
    analyze_position,
    detect_recommendation,
    analyze_citation_depth,
    calculate_share_of_voice,
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

app = FastAPI(title="AEO Dashboard")


# ---------------------------------------------------------------------------
# Core analysis
# ---------------------------------------------------------------------------

async def run_single_query(
    client: BaseLLMClient,
    prompt: str,
    target_domain: str,
) -> dict:
    try:
        resp = await client.query(prompt)
    except Exception as e:
        return {"error": str(e), "cited": False, "urls": [], "query": prompt, "response": "", "response_text": ""}

    text_urls = extract_urls(resp.text)
    all_urls = list(set(text_urls + resp.citations))
    cited = any(target_domain in url for url in all_urls)

    if isinstance(client, MockLLMClient) and not cited:
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
    comp_brands = []
    for c in (competitors or []):
        comp_brands.append(domain_to_brand(c))

    if custom_prompts:
        query_items = [{"prompt": p, "category": "custom", "category_label": "직접 작성"} for p in custom_prompts]
        num_queries = len(query_items)
    else:
        query_items = generate_queries(target_domain, brand, num_queries)

    is_mock = isinstance(client, MockLLMClient)

    if is_mock:
        tasks = [run_single_query(client, q["prompt"], target_domain) for q in query_items]
        results = await asyncio.gather(*tasks)
    else:
        results = []
        for q in query_items:
            r = await run_single_query(client, q["prompt"], target_domain)
            results.append(r)
            await asyncio.sleep(4)

    cited_count = 0
    mentioned_count = 0
    recommended_count = 0
    all_urls: list[str] = []
    errors = 0
    query_details: list[dict] = []
    sentiments: list[dict] = []
    positions: list[dict] = []
    depths: list[dict] = []
    competitor_citations: dict[str, int] = {c: 0 for c in (competitors or [])}
    category_stats: dict[str, dict] = {}
    sov_accumulator: dict[str, int] = {brand: 0}
    for cb in comp_brands:
        sov_accumulator[cb] = 0

    for i, r in enumerate(results):
        resp_text = r.get("response_text", "") or r.get("response", "")
        urls = r.get("urls", [])
        q_info = query_items[i]
        cat = q_info["category"]
        cat_label = q_info["category_label"]

        sent = analyze_sentiment(resp_text, brand)
        sentiments.append(sent)

        pos = analyze_position(resp_text, target_domain, brand)
        positions.append(pos)

        rec = detect_recommendation(resp_text, brand)

        depth = analyze_citation_depth(resp_text, target_domain, brand)
        depths.append(depth)

        brand_mentioned = brand.lower() in resp_text.lower()
        if brand_mentioned:
            mentioned_count += 1

        if rec["recommended"]:
            recommended_count += 1

        # Share of voice accumulation
        if comp_brands:
            sov = calculate_share_of_voice(resp_text, brand, comp_brands)
            for b, cnt in sov["mentions"].items():
                sov_accumulator[b] = sov_accumulator.get(b, 0) + cnt

        for comp in (competitors or []):
            comp_domain = comp.lower().replace("www.", "")
            if any(comp_domain in u.lower() for u in urls) or comp.lower() in resp_text.lower():
                competitor_citations[comp] += 1

        # Category stats
        if cat not in category_stats:
            category_stats[cat] = {"label": cat_label, "total": 0, "cited": 0, "mentioned": 0, "recommended": 0}
        category_stats[cat]["total"] += 1
        if r.get("cited", False):
            category_stats[cat]["cited"] += 1
        if brand_mentioned:
            category_stats[cat]["mentioned"] += 1
        if rec["recommended"]:
            category_stats[cat]["recommended"] += 1

        detail = {
            "query": r.get("query", ""),
            "response": r.get("response", ""),
            "cited": r.get("cited", False),
            "urls": urls,
            "error": r.get("error"),
            "sentiment": sent,
            "position": pos,
            "recommendation": rec,
            "citation_depth": depth,
            "brand_mentioned": brand_mentioned,
            "category": cat,
            "category_label": cat_label,
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
    recommendation_rate = (recommended_count / successful * 100) if successful > 0 else 0
    domain_counts = dict(count_domains(all_urls))

    avg_sentiment = round(
        sum(s["score"] for s in sentiments) / len(sentiments), 2
    ) if sentiments else 0
    sentiment_dist = {"positive": 0, "neutral": 0, "negative": 0}
    for s in sentiments:
        sentiment_dist[s["label"]] += 1

    valid_positions = [p for p in positions if p["section"] != "none"]
    avg_position = round(
        sum(p["position_pct"] for p in valid_positions) / len(valid_positions), 1
    ) if valid_positions else -1
    position_dist = {"top": 0, "middle": 0, "bottom": 0, "none": 0}
    for p in positions:
        position_dist[p["section"]] += 1

    depth_dist = {"linked": 0, "detailed": 0, "surface": 0, "none": 0}
    for d in depths:
        depth_dist[d["depth"]] += 1
    avg_depth = round(
        sum(d["level"] for d in depths) / len(depths), 2
    ) if depths else 0

    comp_rates = {}
    for comp, count in competitor_citations.items():
        comp_rates[comp] = round((count / successful * 100), 1) if successful > 0 else 0

    # Category performance summary
    category_performance = {}
    for cat, stats in category_stats.items():
        t = stats["total"]
        category_performance[cat] = {
            "label": stats["label"],
            "total": t,
            "citation_rate": round(stats["cited"] / t * 100, 1) if t > 0 else 0,
            "mention_rate": round(stats["mentioned"] / t * 100, 1) if t > 0 else 0,
            "recommendation_rate": round(stats["recommended"] / t * 100, 1) if t > 0 else 0,
        }

    # Share of voice
    sov_total = sum(sov_accumulator.values())
    share_of_voice = {}
    for b, cnt in sov_accumulator.items():
        share_of_voice[b] = round(cnt / sov_total * 100, 1) if sov_total > 0 else 0

    # AEO composite score (0-100)
    sent_norm = (avg_sentiment + 1) / 2 * 100  # -1..1 → 0..100
    if avg_position >= 0:
        pos_norm = max(0, 100 - avg_position)  # 0% position = 100 score
    else:
        pos_norm = 0
    aeo_score = round(
        citation_rate * 0.25
        + mention_rate * 0.20
        + recommendation_rate * 0.20
        + sent_norm * 0.15
        + pos_norm * 0.20,
        1,
    )

    return {
        "llm": client.name,
        "mode": "mock" if is_mock else "live",
        "total_queries": num_queries,
        "successful_queries": successful,
        "errors": errors,
        "cited_count": cited_count,
        "citation_rate": round(citation_rate, 1),
        "mention_rate": round(mention_rate, 1),
        "recommendation_rate": round(recommendation_rate, 1),
        "avg_sentiment": avg_sentiment,
        "sentiment_dist": sentiment_dist,
        "avg_position": avg_position,
        "position_dist": position_dist,
        "depth_dist": depth_dist,
        "avg_depth": avg_depth,
        "competitor_rates": comp_rates,
        "share_of_voice": share_of_voice,
        "category_performance": category_performance,
        "aeo_score": aeo_score,
        "top_domains": dict(
            sorted(domain_counts.items(), key=lambda x: -x[1])[:10]
        ),
        "target_domain_urls": [u for u in all_urls if target_domain in u],
        "query_details": query_details,
    }


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    url: str
    num_queries: int = 10
    custom_prompts: list[str] | None = None
    competitors: list[str] | None = None


@app.get("/api/status")
async def llm_status():
    return get_status()


@app.post("/api/analyze")
async def analyze_citation(req: AnalyzeRequest):
    parsed = urlparse(req.url if "://" in req.url else f"https://{req.url}")
    target_domain = parsed.netloc or parsed.path.split("/")[0]
    brand = domain_to_brand(target_domain)

    clients = get_active_clients(use_mock_fallback=True)
    tasks = [
        analyze_llm(c, target_domain, brand, req.num_queries, req.custom_prompts, req.competitors)
        for c in clients
    ]
    results = await asyncio.gather(*tasks)
    sorted_results = sorted(results, key=lambda r: -r["citation_rate"])

    # Global AEO score
    aeo_scores = [r["aeo_score"] for r in sorted_results]
    global_aeo = round(sum(aeo_scores) / len(aeo_scores), 1) if aeo_scores else 0

    return {
        "target_url": req.url,
        "target_domain": target_domain,
        "brand": brand,
        "global_aeo_score": global_aeo,
        "results": sorted_results,
    }


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
