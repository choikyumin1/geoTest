"""
URL Extraction and AEO Analysis Utility

Extracts URLs from text responses and provides comprehensive AEO
(Answer Engine Optimization) analytics including sentiment analysis,
recommendation detection, citation depth, and position analysis.
"""

import re
from collections import Counter
from urllib.parse import urlparse


def extract_urls(text: str) -> list[str]:
    return re.findall(r'https?://[^\s\)\]\}\>\,\"\']+'  , text)


def get_domains(urls: list[str]) -> list[str]:
    return [urlparse(url).netloc for url in urls]


def count_domains(urls: list[str]) -> Counter:
    return Counter(get_domains(urls))


def group_urls_by_domain(urls: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for url in urls:
        domain = urlparse(url).netloc
        grouped.setdefault(domain, []).append(url)
    return grouped


def extract_brand_mentions(text: str, brands: list[str]) -> dict[str, int]:
    mentions: dict[str, int] = {}
    for brand in brands:
        pattern = re.compile(re.escape(brand), re.IGNORECASE)
        count = len(pattern.findall(text))
        if count > 0:
            mentions[brand] = count
    return mentions


def analyze_response(text: str, brands: list[str] | None = None) -> dict:
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
# Improved Sentiment Analysis (negation-aware, weighted)
# ---------------------------------------------------------------------------

NEGATION_WORDS = {
    "not", "no", "never", "neither", "nor", "isn't", "wasn't", "doesn't",
    "don't", "won't", "can't", "couldn't", "shouldn't", "wouldn't",
    "hardly", "barely", "scarcely", "lack", "without",
}

POSITIVE_W = {
    "best": 2, "excellent": 2, "outstanding": 2, "superior": 2,
    "exceptional": 2, "perfect": 2, "remarkable": 1.8,
    "great": 1.5, "innovative": 1.5, "recommended": 2, "pioneering": 1.5,
    "brilliant": 1.5, "impressive": 1.5, "trusted": 1.5, "reliable": 1.5,
    "renowned": 1.5, "favorite": 1.5, "preferred": 1.5, "success": 1.5,
    "award": 1.5, "ideal": 1.5, "leading": 1.5,
    "top": 1, "popular": 1, "premium": 1, "advanced": 1, "powerful": 1,
    "efficient": 1, "quality": 1, "strong": 1, "growth": 1, "robust": 1,
    "proven": 1, "advantage": 1, "dominant": 1,
}

NEGATIVE_W = {
    "worst": 2, "terrible": 2, "awful": 2, "horrible": 2, "disastrous": 2,
    "poor": 1.5, "bad": 1.5, "disappointing": 1.5, "failing": 1.5,
    "unreliable": 1.5, "inferior": 1.5, "controversy": 1.5, "lawsuit": 1.5,
    "recall": 1.5, "defect": 1.5, "flawed": 1.5, "broken": 1.5,
    "issue": 1, "problem": 1, "complaint": 1, "expensive": 1,
    "overpriced": 1, "slow": 1, "buggy": 1, "outdated": 1, "weak": 1,
    "criticism": 1, "decline": 1, "loss": 1, "lag": 1, "behind": 1,
    "lacks": 1, "limited": 0.5, "concern": 0.5, "risk": 0.5,
}


def analyze_sentiment(text: str, brand: str) -> dict:
    text_lower = text.lower()
    brand_lower = brand.lower()

    if brand_lower not in text_lower:
        return {"score": 0, "label": "neutral", "positive": 0, "negative": 0}

    contexts = []
    for match in re.finditer(re.escape(brand_lower), text_lower):
        start = max(0, match.start() - 250)
        end = min(len(text_lower), match.end() + 250)
        contexts.append(text_lower[start:end])

    context_text = " ".join(contexts) if contexts else text_lower
    words = re.findall(r"[a-z']+", context_text)

    pos_score = 0.0
    neg_score = 0.0

    for i, word in enumerate(words):
        negated = any(
            words[j] in NEGATION_WORDS
            for j in range(max(0, i - 3), i)
        )

        if word in POSITIVE_W:
            w = POSITIVE_W[word]
            if negated:
                neg_score += w * 0.6
            else:
                pos_score += w

        if word in NEGATIVE_W:
            w = NEGATIVE_W[word]
            if negated:
                pos_score += w * 0.4
            else:
                neg_score += w

    total = pos_score + neg_score
    if total == 0:
        return {"score": 0, "label": "neutral", "positive": 0, "negative": 0}

    score = round((pos_score - neg_score) / total, 2)
    label = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")

    return {
        "score": score,
        "label": label,
        "positive": round(pos_score, 1),
        "negative": round(neg_score, 1),
    }


# ---------------------------------------------------------------------------
# Citation Position Analysis
# ---------------------------------------------------------------------------

def analyze_position(text: str, target_domain: str, brand: str) -> dict:
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


# ---------------------------------------------------------------------------
# Recommendation Detection
# ---------------------------------------------------------------------------

RECOMMEND_PATTERNS = [
    r"\brecommend(?:s|ed|ing)?\b[^.]{0,60}{brand}",
    r"{brand}[^.]{0,60}\brecommend(?:s|ed|ing)?\b",
    r"\bsuggest(?:s|ed|ing)?\b[^.]{0,60}{brand}",
    r"{brand}[^.]{0,80}(?:is|are)\s+(?:a\s+)?(?:great|excellent|top|best|ideal|perfect)\s+(?:choice|option|pick|solution)",
    r"(?:go\s+with|opt\s+for|choose|consider|try)\s+{brand}",
    r"{brand}\s+(?:is|are)\s+(?:highly\s+)?recommended",
    r"(?:best|top|leading)\s+(?:choice|option|pick|recommendation)[^.]{0,40}{brand}",
    r"{brand}[^.]{0,60}(?:stands?\s+out|excels?|leads?\s+the)",
    r"(?:would|should|could)\s+(?:recommend|suggest)[^.]{0,40}{brand}",
    r"{brand}[^.]{0,40}(?:worth\s+(?:considering|trying|checking))",
]


def detect_recommendation(text: str, brand: str) -> dict:
    text_lower = text.lower()
    brand_lower = brand.lower()
    brand_escaped = re.escape(brand_lower)

    if brand_lower not in text_lower:
        return {"recommended": False, "confidence": 0, "patterns_matched": 0}

    matched = 0
    for tmpl in RECOMMEND_PATTERNS:
        pattern = tmpl.replace("{brand}", brand_escaped)
        if re.search(pattern, text_lower):
            matched += 1

    if matched >= 3:
        confidence = 1.0
    elif matched == 2:
        confidence = 0.8
    elif matched == 1:
        confidence = 0.6
    else:
        confidence = 0.0

    return {
        "recommended": matched > 0,
        "confidence": round(confidence, 2),
        "patterns_matched": matched,
    }


# ---------------------------------------------------------------------------
# Citation Depth Analysis
# ---------------------------------------------------------------------------

def analyze_citation_depth(text: str, target_domain: str, brand: str) -> dict:
    """
    linked:   URL with target domain present + substantial discussion
    detailed: Brand discussed substantially without URL
    surface:  Brand mentioned briefly
    none:     Not mentioned
    """
    text_lower = text.lower()
    brand_lower = brand.lower()

    has_url = any(target_domain.lower() in u.lower() for u in extract_urls(text))

    if brand_lower not in text_lower and not has_url:
        return {"depth": "none", "level": 0}

    sentences = re.split(r'[.!?\n]+', text)
    brand_sentences = [s for s in sentences if brand_lower in s.lower()]
    brand_char_count = sum(len(s.strip()) for s in brand_sentences)

    if has_url and (len(brand_sentences) >= 3 or brand_char_count >= 150):
        return {"depth": "linked", "level": 4}
    elif has_url:
        return {"depth": "linked", "level": 3}
    elif len(brand_sentences) >= 3 or brand_char_count >= 150:
        return {"depth": "detailed", "level": 2}
    elif brand_lower in text_lower:
        return {"depth": "surface", "level": 1}
    else:
        return {"depth": "none", "level": 0}


# ---------------------------------------------------------------------------
# Share of Voice
# ---------------------------------------------------------------------------

def calculate_share_of_voice(
    text: str,
    target_brand: str,
    competitor_brands: list[str],
) -> dict:
    all_brands = [target_brand] + competitor_brands
    mentions: dict[str, int] = {}

    text_lower = text.lower()
    for b in all_brands:
        mentions[b] = len(re.findall(re.escape(b.lower()), text_lower))

    total = sum(mentions.values())
    shares: dict[str, float] = {}
    for b in all_brands:
        shares[b] = round((mentions[b] / total * 100), 1) if total > 0 else 0

    return {
        "mentions": mentions,
        "shares": shares,
        "total_mentions": total,
        "target_share": shares.get(target_brand, 0),
    }
