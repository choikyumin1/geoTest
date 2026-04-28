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

def generate_insights(results: list[dict], brand: str, domain: str, competitors: list[str]) -> dict:
    n = len(results)
    if n == 0:
        return {"metric_insights": [], "integrated": {}}

    avg = lambda vals: round(sum(vals) / len(vals), 1) if vals else 0
    cite_rates = [r["citation_rate"] for r in results]
    mention_rates = [r["mention_rate"] for r in results]
    rec_rates = [r["recommendation_rate"] for r in results]
    sentiments = [r["avg_sentiment"] for r in results]
    positions = [r["avg_position"] for r in results if r["avg_position"] >= 0]
    depths = [r["avg_depth"] for r in results]
    aeo_scores = [r["aeo_score"] for r in results]

    avg_cite = avg(cite_rates)
    avg_mention = avg(mention_rates)
    avg_rec = avg(rec_rates)
    avg_sent = avg(sentiments)
    avg_pos = avg(positions)
    avg_dep = avg(depths)
    avg_aeo = avg(aeo_scores)

    best_llm = max(results, key=lambda r: r["aeo_score"])
    worst_llm = min(results, key=lambda r: r["aeo_score"])

    metrics = []

    # 1. Citation Rate
    if avg_cite >= 70:
        status, summary = "good", f"{brand}의 URL이 평균 {avg_cite}%의 높은 비율로 인용되고 있습니다."
        recs = ["현재 수준을 유지하면서 인용 품질(Depth)을 높이는 데 집중하세요.", "인용되는 페이지의 콘텐츠를 최신 상태로 유지하세요."]
    elif avg_cite >= 30:
        status, summary = "warning", f"{brand}의 URL 인용율이 평균 {avg_cite}%로 보통 수준입니다."
        recs = ["Schema.org 구조화 데이터 마크업을 추가하여 LLM의 정보 인식을 개선하세요.", "권위 있는 외부 사이트(위키피디아, 언론)에서 백링크를 확보하세요.", "FAQ 페이지를 만들어 LLM이 자주 답변하는 질문에 맞는 콘텐츠를 제공하세요."]
    else:
        status, summary = "critical", f"{brand}의 URL 인용율이 평균 {avg_cite}%로 매우 낮습니다. LLM이 출처로 인식하지 못하고 있습니다."
        recs = ["도메인 권위(Domain Authority)를 높이기 위한 SEO 기초 작업이 시급합니다.", "업계 권위 사이트, 학술 자료, 뉴스 매체에서의 브랜드 언급을 확대하세요.", "E-E-A-T(경험, 전문성, 권위, 신뢰) 기반 콘텐츠를 강화하세요."]
    metrics.append({"metric": "citation_rate", "title": "인용율 (Citation Rate)", "status": status, "summary": summary, "recommendations": recs})

    # 2. Mention Rate
    if avg_mention >= 70:
        status, summary = "good", f"{brand}이(가) 평균 {avg_mention}%의 응답에서 언급되고 있습니다."
        recs = ["언급의 맥락이 긍정적인지 감성 분석과 함께 모니터링하세요.", "브랜드 연관 키워드를 다양화하여 더 넓은 주제에서 언급되도록 하세요."]
    elif avg_mention >= 30:
        status, summary = "warning", f"{brand}의 브랜드 언급율이 평균 {avg_mention}%입니다."
        recs = ["브랜드 관련 고품질 콘텐츠(블로그, 보고서, 사례 연구)를 지속 발행하세요.", "업계 키워드와 브랜드를 연결하는 콘텐츠 전략을 수립하세요.", "소셜 미디어, 포럼 등에서 브랜드 가시성을 높이세요."]
    else:
        status, summary = "critical", f"{brand}의 브랜드 언급율이 평균 {avg_mention}%로 매우 낮습니다. 대부분의 LLM이 브랜드를 인식하지 못합니다."
        recs = ["위키피디아 페이지 생성/보강을 최우선으로 진행하세요.", "주요 언론 매체를 통한 브랜드 노출을 확대하세요.", "업계 보고서, 학술 논문 등 LLM 학습 데이터에 포함될 수 있는 채널에 진출하세요."]
    metrics.append({"metric": "mention_rate", "title": "멘션율 (Mention Rate)", "status": status, "summary": summary, "recommendations": recs})

    # 3. Recommendation Rate
    if avg_rec >= 50:
        status, summary = "good", f"LLM이 평균 {avg_rec}%의 응답에서 {brand}을(를) 추천하고 있습니다."
        recs = ["추천 맥락을 분석하여 어떤 강점이 부각되는지 파악하고 마케팅에 활용하세요.", "추천 빈도가 높은 LLM의 패턴을 다른 LLM에도 적용할 수 있는 콘텐츠를 만드세요."]
    elif avg_rec >= 20:
        status, summary = "warning", f"{brand}의 추천율이 평균 {avg_rec}%입니다. 개선 여지가 있습니다."
        recs = ["고객 리뷰, 수상 이력, 인증 정보를 웹사이트에 구조화하여 게시하세요.", "'Best', 'Top', 'Recommended' 키워드가 포함된 비교/추천 콘텐츠를 제작하세요.", "제3자 리뷰 사이트에서 긍정적 평가를 확보하세요."]
    else:
        status, summary = "critical", f"{brand}의 추천율이 평균 {avg_rec}%로 매우 낮습니다. LLM이 브랜드를 추천 대상으로 고려하지 않습니다."
        recs = ["경쟁사 대비 차별화 포인트를 명확히 하는 콘텐츠를 만드세요.", "신뢰할 수 있는 리뷰/비교 사이트에서 브랜드 프로필을 강화하세요.", "사용 사례(Case Study)와 성공 스토리를 다양한 채널에 게시하세요."]
    metrics.append({"metric": "recommendation_rate", "title": "추천율 (Recommendation Rate)", "status": status, "summary": summary, "recommendations": recs})

    # 4. Sentiment
    if avg_sent > 0.15:
        status, summary = "good", f"{brand}에 대한 LLM의 감성이 긍정적입니다 (점수: {avg_sent})."
        recs = ["긍정적 이미지를 유지하면서 부정적 이슈 발생 시 빠르게 대응하는 모니터링 체계를 갖추세요.", "긍정적 맥락에서 자주 언급되는 키워드를 파악하여 콘텐츠 전략에 반영하세요."]
    elif avg_sent > -0.15:
        status, summary = "warning", f"{brand}에 대한 감성이 중립적입니다 (점수: {avg_sent})."
        recs = ["브랜드 강점과 성과를 강조하는 콘텐츠를 제작하여 긍정적 감성을 유도하세요.", "고객 성공 사례, 수상 이력 등 긍정적 시그널을 웹에 확산시키세요.", "부정적 키워드와 연관된 이슈가 있다면 공식 입장을 통해 해소하세요."]
    else:
        status, summary = "critical", f"{brand}에 대한 감성이 부정적입니다 (점수: {avg_sent}). LLM이 부정적 맥락에서 브랜드를 언급합니다."
        recs = ["부정적으로 언급되는 구체적 이슈를 파악하고 공식 대응 콘텐츠를 발행하세요.", "긍정적 뉴스, 혁신 사례, CSR 활동 등을 적극적으로 홍보하세요.", "리뷰 관리와 고객 불만 해소에 집중하세요."]
    metrics.append({"metric": "sentiment", "title": "감성 분석 (Sentiment)", "status": status, "summary": summary, "recommendations": recs})

    # 5. Position
    if positions:
        if avg_pos <= 33:
            status, summary = "good", f"{brand}이(가) LLM 응답 상단(평균 {avg_pos}%)에 노출되고 있습니다."
            recs = ["상단 노출을 유지하기 위해 콘텐츠의 신선도와 권위를 지속 관리하세요.", "다양한 질문 유형에서도 상단 노출이 유지되는지 카테고리별 성과를 확인하세요."]
        elif avg_pos <= 66:
            status, summary = "warning", f"{brand}이(가) LLM 응답 중간(평균 {avg_pos}%)에 노출됩니다."
            recs = ["질문에 직접 답변하는 형태의 콘텐츠(FAQ, How-to)를 강화하세요.", "브랜드가 해당 분야의 '대표' 또는 '최고'로 인식되도록 권위 있는 콘텐츠를 확보하세요."]
        else:
            status, summary = "critical", f"{brand}이(가) LLM 응답 하단(평균 {avg_pos}%)에서만 언급됩니다."
            recs = ["브랜드와 핵심 키워드의 연관성을 강화하는 콘텐츠를 최우선으로 제작하세요.", "경쟁사보다 먼저 언급될 수 있도록 독보적인 전문성 콘텐츠를 구축하세요."]
    else:
        status, summary = "critical", f"{brand}이(가) 대부분의 LLM 응답에서 언급되지 않아 위치 데이터가 없습니다."
        recs = ["브랜드 인지도 자체를 높이는 것이 선행되어야 합니다. 멘션율 개선 권장사항을 먼저 실행하세요."]
    metrics.append({"metric": "position", "title": "인용 위치 (Position)", "status": status, "summary": summary, "recommendations": recs})

    # 6. Citation Depth
    if avg_dep >= 3:
        status, summary = "good", f"평균 인용 깊이가 {avg_dep}/4로 높습니다. LLM이 URL과 함께 상세히 설명합니다."
        recs = ["링크가 연결되는 랜딩 페이지의 사용자 경험을 최적화하세요.", "인용되는 콘텐츠가 최신 정보를 반영하도록 주기적으로 업데이트하세요."]
    elif avg_dep >= 1.5:
        status, summary = "warning", f"평균 인용 깊이가 {avg_dep}/4입니다. 브랜드가 언급되지만 URL 인용이 부족합니다."
        recs = ["웹사이트의 기술적 SEO(사이트맵, 크롤링 최적화)를 점검하세요.", "각 주제별 전문 랜딩 페이지를 만들어 LLM이 특정 URL을 인용할 수 있게 하세요.", "데이터, 통계, 리서치 등 인용 가치가 높은 콘텐츠를 제작하세요."]
    else:
        status, summary = "critical", f"평균 인용 깊이가 {avg_dep}/4로 매우 낮습니다."
        recs = ["웹사이트의 콘텐츠 품질과 구조를 전면 개선하세요.", "LLM이 참조할 수 있는 리서치 보고서, 백서 등 권위 있는 자료를 발행하세요."]
    metrics.append({"metric": "citation_depth", "title": "인용 깊이 (Citation Depth)", "status": status, "summary": summary, "recommendations": recs})

    # 7. Category Performance
    all_cats = {}
    for r in results:
        for cat, perf in r.get("category_performance", {}).items():
            if cat not in all_cats:
                all_cats[cat] = {"label": perf["label"], "rates": []}
            all_cats[cat]["rates"].append(perf["citation_rate"])

    if all_cats:
        cat_avgs = {k: {"label": v["label"], "avg": avg(v["rates"])} for k, v in all_cats.items()}
        best_cat = max(cat_avgs.items(), key=lambda x: x[1]["avg"])
        worst_cat = min(cat_avgs.items(), key=lambda x: x[1]["avg"])

        if worst_cat[1]["avg"] >= 50:
            status = "good"
        elif worst_cat[1]["avg"] >= 20:
            status = "warning"
        else:
            status = "critical"

        summary = f"가장 강한 카테고리: {best_cat[1]['label']} ({best_cat[1]['avg']}%), 가장 약한 카테고리: {worst_cat[1]['label']} ({worst_cat[1]['avg']}%)"
        recs = []
        if worst_cat[1]["avg"] < best_cat[1]["avg"] - 20:
            cat_recs = {
                "comparison": "경쟁사 대비 비교 콘텐츠, 장단점 분석 자료를 강화하세요.",
                "transactional": "제품 리뷰, 추천 가이드, 구매 가이드 콘텐츠를 제작하세요.",
                "problem_solving": "FAQ, 문제 해결 가이드, 트러블슈팅 문서를 보강하세요.",
                "reputation": "보도자료, 수상 이력, 업계 리더십 콘텐츠를 확대하세요.",
                "informational": "브랜드 소개, 회사 연혁, 제품 정보 페이지를 최적화하세요.",
            }
            recs.append(f"'{worst_cat[1]['label']}' 카테고리에서 인용율이 {worst_cat[1]['avg']}%로 가장 낮습니다.")
            if worst_cat[0] in cat_recs:
                recs.append(cat_recs[worst_cat[0]])
        recs.append(f"'{best_cat[1]['label']}' 카테고리의 성공 패턴을 분석하여 다른 카테고리에 적용하세요.")
        metrics.append({"metric": "category", "title": "카테고리별 성과", "status": status, "summary": summary, "recommendations": recs})

    # 8. Competitor / SOV
    if competitors:
        comp_insights = []
        for r in results:
            for comp, rate in r.get("competitor_rates", {}).items():
                comp_insights.append({"comp": comp, "rate": rate, "llm": r["llm"]})

        target_avg = avg_cite
        comp_avgs = {}
        for comp in competitors:
            rates = [ci["rate"] for ci in comp_insights if ci["comp"] == comp]
            comp_avgs[comp] = avg(rates)

        losing_to = [c for c, r in comp_avgs.items() if r > target_avg]
        winning_over = [c for c, r in comp_avgs.items() if r <= target_avg]

        if not losing_to:
            status, summary = "good", f"{brand}이(가) 모든 경쟁사보다 높은 인용율을 보이고 있습니다."
            recs = ["경쟁 우위를 유지하면서 시장 변화를 주기적으로 모니터링하세요."]
        elif len(losing_to) < len(competitors):
            status = "warning"
            summary = f"{', '.join(losing_to)}에 인용율이 뒤처지고 있습니다."
            recs = [f"{c} 대비 차별화 콘텐츠를 강화하세요." for c in losing_to]
        else:
            status = "critical"
            summary = f"모든 경쟁사({', '.join(losing_to)})에 인용율이 뒤처지고 있습니다."
            recs = ["경쟁사 콘텐츠 전략을 분석하여 벤치마킹하세요.", "브랜드만의 고유한 전문성 영역을 개발하여 차별화하세요."]

        sov_data = {}
        for r in results:
            for b, s in r.get("share_of_voice", {}).items():
                sov_data[b] = sov_data.get(b, 0) + s
        total_sov = sum(sov_data.values())
        if total_sov > 0:
            target_sov = round(sov_data.get(brand, 0) / total_sov * 100, 1)
            recs.append(f"현재 Share of Voice: {target_sov}%. {'시장 지배력이 양호합니다.' if target_sov >= 40 else '점유율 확대가 필요합니다.'}")

        metrics.append({"metric": "competitor", "title": "경쟁사 비교 / Share of Voice", "status": status, "summary": summary, "recommendations": recs})

    # Integrated insight
    strengths = []
    weaknesses = []
    actions = []

    for m in metrics:
        if m["status"] == "good":
            strengths.append(m["title"])
        elif m["status"] == "critical":
            weaknesses.append(m["title"])
            if m["recommendations"]:
                actions.append(m["recommendations"][0])

    if avg_aeo >= 70:
        grade = "A"
        overall = f"{brand}의 AEO 상태가 우수합니다 (평균 {avg_aeo}점). 현재 전략을 유지하면서 세부 최적화에 집중하세요."
    elif avg_aeo >= 50:
        grade = "B"
        overall = f"{brand}의 AEO 상태가 양호합니다 (평균 {avg_aeo}점). 약점 영역을 보완하면 크게 개선될 수 있습니다."
    elif avg_aeo >= 30:
        grade = "C"
        overall = f"{brand}의 AEO 상태가 보통입니다 (평균 {avg_aeo}점). 체계적인 AEO 전략 수립이 필요합니다."
    else:
        grade = "D"
        overall = f"{brand}의 AEO 상태가 취약합니다 (평균 {avg_aeo}점). LLM 생태계에서 브랜드 존재감을 구축하는 것이 시급합니다."

    llm_summary = f"가장 높은 AEO 점수: {best_llm['llm']} ({best_llm['aeo_score']}점), 가장 낮은 점수: {worst_llm['llm']} ({worst_llm['aeo_score']}점)"

    integrated = {
        "grade": grade,
        "aeo_score": avg_aeo,
        "overall": overall,
        "llm_summary": llm_summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "priority_actions": actions[:5],
    }

    return {"metric_insights": metrics, "integrated": integrated}


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
        "insights": generate_insights(sorted_results, brand, target_domain, req.competitors or []),
    }


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index():
    return FileResponse("static/index.html")
