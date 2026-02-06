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
