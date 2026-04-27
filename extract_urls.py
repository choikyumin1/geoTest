"""
URL Extraction and Domain Counting Utility

Extracts URLs from text responses and provides domain-level analytics
including frequency counting, grouping, and citation analysis.
"""

import re
from collections import Counter
from urllib.parse import urlparse


def extract_urls(text: str) -> list[str]:
    """Extract all HTTP/HTTPS URLs from text."""
    return re.findall(r'https?://[^\s\)\]\}\>\,\"\']+'  , text)


def get_domains(urls: list[str]) -> list[str]:
    """Parse domain (netloc) from each URL."""
    return [urlparse(url).netloc for url in urls]


def count_domains(urls: list[str]) -> Counter:
    """Count URL occurrences per domain."""
    domains = get_domains(urls)
    return Counter(domains)


def group_urls_by_domain(urls: list[str]) -> dict[str, list[str]]:
    """Group URLs by their domain."""
    grouped: dict[str, list[str]] = {}
    for url in urls:
        domain = urlparse(url).netloc
        grouped.setdefault(domain, []).append(url)
    return grouped


def extract_brand_mentions(text: str, brands: list[str]) -> dict[str, int]:
    """
    Count brand/site name mentions in text (NLP-lite approach).
    Matches patterns like "according to <brand>" or "<brand> reports".
    """
    mentions: dict[str, int] = {}
    for brand in brands:
        pattern = re.compile(re.escape(brand), re.IGNORECASE)
        count = len(pattern.findall(text))
        if count > 0:
            mentions[brand] = count
    return mentions


def analyze_response(text: str, brands: list[str] | None = None) -> dict:
    """
    Full analysis of a response text:
    - Extract URLs
    - Count by domain
    - Group by domain
    - Optionally count brand mentions
    """
    urls = extract_urls(text)
    result = {
        "urls": urls,
        "total_url_count": len(urls),
        "domain_counts": dict(count_domains(urls)),
        "urls_by_domain": group_urls_by_domain(urls),
    }
    if brands:
        result["brand_mentions"] = extract_brand_mentions(text, brands)
    return result


# ---------------------------------------------------------------------------
# Sentiment analysis (keyword-based)
# ---------------------------------------------------------------------------

POSITIVE_WORDS = {
    "best", "great", "excellent", "leading", "innovative", "recommended",
    "top", "popular", "trusted", "reliable", "award", "outstanding",
    "superior", "premium", "advanced", "powerful", "impressive",
    "efficient", "quality", "favorite", "renowned", "pioneering",
    "success", "advantage", "strong", "dominat", "growth",
}

NEGATIVE_WORDS = {
    "worst", "poor", "bad", "issue", "problem", "complaint",
    "expensive", "overpriced", "disappointing", "failing", "slow",
    "buggy", "unreliable", "inferior", "outdated", "weak",
    "controversy", "lawsuit", "recall", "defect", "criticism",
    "decline", "loss", "risk", "lag", "behind",
}


def analyze_sentiment(text: str, brand: str) -> dict:
    """Analyze sentiment of text around brand mentions."""
    text_lower = text.lower()
    brand_lower = brand.lower()

    if brand_lower not in text_lower:
        return {"score": 0, "label": "neutral", "positive": 0, "negative": 0}

    # Extract context windows around each brand mention
    contexts = []
    for match in re.finditer(re.escape(brand_lower), text_lower):
        start = max(0, match.start() - 200)
        end = min(len(text_lower), match.end() + 200)
        contexts.append(text_lower[start:end])

    context_text = " ".join(contexts) if contexts else text_lower
    words = set(re.findall(r"[a-z]+", context_text))

    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)

    total = pos + neg
    if total == 0:
        return {"score": 0, "label": "neutral", "positive": 0, "negative": 0}

    score = round((pos - neg) / total, 2)
    if score > 0.2:
        label = "positive"
    elif score < -0.2:
        label = "negative"
    else:
        label = "neutral"

    return {"score": score, "label": label, "positive": pos, "negative": neg}


# ---------------------------------------------------------------------------
# Citation position analysis
# ---------------------------------------------------------------------------

def analyze_position(text: str, target_domain: str, brand: str) -> dict:
    """Analyze where in the response the brand/URL first appears."""
    text_lower = text.lower()
    text_len = len(text_lower)

    if text_len == 0:
        return {"position_pct": -1, "section": "none"}

    domain_pos = text_lower.find(target_domain.lower())
    brand_pos = text_lower.find(brand.lower())

    positions = [p for p in [domain_pos, brand_pos] if p >= 0]

    if not positions:
        return {"position_pct": -1, "section": "none"}

    first_pos = min(positions)
    pct = round(first_pos / text_len * 100, 1)

    if pct <= 33:
        section = "top"
    elif pct <= 66:
        section = "middle"
    else:
        section = "bottom"

    return {"position_pct": pct, "section": section}


if __name__ == "__main__":
    sample_text = """
    According to Samsung Healthcare, the new device improves diagnostics.
    See https://www.samsung.com/healthcare/product1 for details.
    More info at https://www.samsung.com/healthcare/product2 and
    https://docs.python.org/3/library/urllib.parse.html
    Also check https://developer.mozilla.org/en-US/docs/Web and
    https://developer.mozilla.org/en-US/docs/Learn for learning resources.
    Samsung Healthcare also published a report at https://www.samsung.com/report.pdf
    """

    result = analyze_response(sample_text, brands=["Samsung Healthcare", "Mozilla"])

    print("=== URL Extraction & Domain Analysis ===\n")
    print(f"Total URLs found: {result['total_url_count']}\n")

    print("Domain counts:")
    for domain, count in sorted(result["domain_counts"].items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count}")

    print("\nURLs grouped by domain:")
    for domain, urls in result["urls_by_domain"].items():
        print(f"\n  [{domain}]")
        for url in urls:
            print(f"    - {url}")

    if result.get("brand_mentions"):
        print("\nBrand mentions:")
        for brand, count in result["brand_mentions"].items():
            print(f"  {brand}: {count}")
