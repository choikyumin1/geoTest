# geoTest

URL extraction and domain-level analytics utility.

## Features

- Extract HTTP/HTTPS URLs from text using regex
- Count URLs per domain
- Group URLs by domain
- Detect brand/site name mentions in text (case-insensitive)
- Combined `analyze_response()` for full pipeline analysis

## Usage

```python
from extract_urls import analyze_response

text = "Check https://example.com/a and https://other.org/b. Example Corp is great."
result = analyze_response(text, brands=["Example Corp"])

print(result["domain_counts"])    # {'example.com': 1, 'other.org': 1}
print(result["brand_mentions"])   # {'Example Corp': 1}
```

## Run demo

```bash
python extract_urls.py
```

## Run tests

```bash
python -m unittest test_extract_urls -v
```
