"""Tests for extract_urls module."""

import unittest
from extract_urls import (
    extract_urls,
    get_domains,
    count_domains,
    group_urls_by_domain,
    extract_brand_mentions,
    analyze_response,
)


class TestExtractUrls(unittest.TestCase):
    def test_extract_http_and_https(self):
        text = "Visit http://example.com and https://secure.example.com"
        urls = extract_urls(text)
        self.assertEqual(len(urls), 2)
        self.assertIn("http://example.com", urls)
        self.assertIn("https://secure.example.com", urls)

    def test_extract_urls_with_paths(self):
        text = "See https://example.com/path/to/page?q=1&lang=en"
        urls = extract_urls(text)
        self.assertEqual(len(urls), 1)
        self.assertIn("https://example.com/path/to/page?q=1&lang=en", urls)

    def test_extract_urls_in_parentheses(self):
        text = "(https://example.com/page)"
        urls = extract_urls(text)
        self.assertEqual(urls, ["https://example.com/page"])

    def test_no_urls(self):
        text = "No links here, just plain text."
        urls = extract_urls(text)
        self.assertEqual(urls, [])


class TestGetDomains(unittest.TestCase):
    def test_basic_domains(self):
        urls = ["https://a.com/x", "https://b.org/y", "https://a.com/z"]
        domains = get_domains(urls)
        self.assertEqual(domains, ["a.com", "b.org", "a.com"])


class TestCountDomains(unittest.TestCase):
    def test_counting(self):
        urls = [
            "https://a.com/1",
            "https://b.com/2",
            "https://a.com/3",
            "https://a.com/4",
        ]
        counts = count_domains(urls)
        self.assertEqual(counts["a.com"], 3)
        self.assertEqual(counts["b.com"], 1)


class TestGroupUrlsByDomain(unittest.TestCase):
    def test_grouping(self):
        urls = [
            "https://a.com/1",
            "https://b.com/2",
            "https://a.com/3",
        ]
        grouped = group_urls_by_domain(urls)
        self.assertEqual(len(grouped["a.com"]), 2)
        self.assertEqual(len(grouped["b.com"]), 1)


class TestBrandMentions(unittest.TestCase):
    def test_case_insensitive(self):
        text = "samsung Healthcare said something. SAMSUNG HEALTHCARE confirmed."
        mentions = extract_brand_mentions(text, ["Samsung Healthcare"])
        self.assertEqual(mentions["Samsung Healthcare"], 2)

    def test_no_match(self):
        text = "Nothing relevant here."
        mentions = extract_brand_mentions(text, ["Apple"])
        self.assertEqual(mentions, {})


class TestAnalyzeResponse(unittest.TestCase):
    def test_full_analysis(self):
        text = (
            "Check https://example.com/a and https://example.com/b "
            "and https://other.org/c. Example Corp is great."
        )
        result = analyze_response(text, brands=["Example Corp"])
        self.assertEqual(result["total_url_count"], 3)
        self.assertEqual(result["domain_counts"]["example.com"], 2)
        self.assertEqual(result["domain_counts"]["other.org"], 1)
        self.assertEqual(len(result["urls_by_domain"]["example.com"]), 2)
        self.assertEqual(result["brand_mentions"]["Example Corp"], 1)

    def test_without_brands(self):
        text = "Visit https://example.com"
        result = analyze_response(text)
        self.assertNotIn("brand_mentions", result)


if __name__ == "__main__":
    unittest.main()
