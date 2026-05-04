# Trafilatura Python Library - Technical Summary

**Source**: https://trafilatura.readthedocs.io/en/latest/usage-python.html
**Fetched**: 2026-05-04T00:00:00Z

---

## Installation

Additional components for language identification: `pip install trafilatura[all]`

## Core Extraction Functions

Import via `from trafilatura import ...`:

- **`extract()`**: "Wrapper function, easiest way to perform text extraction and conversion"
- **`bare_extraction()`**: Returns bare Python variables, bypasses output conversion
- **`baseline()`**: Faster extraction, returns tuple `(postbody, text, len_text)`
- **`html2txt()`**: Extracts all text, maximizes recall (last resort)

## Output Formats

Use `output_format` parameter: `"csv", "json", "html", "markdown", "txt", "xml", "xmltei"`

`bare_extraction` also accepts `"python"` format.

## Key `extract()` Parameters

**HTML Elements:**
- `include_comments=True` (default)
- `include_tables=True` (default)
- `include_formatting=True` - keeps `<b>`, `<strong>`, `<i>`, etc.
- `include_links=True` - keeps href targets
- `include_images=True` - keeps `<img>` attributes

**Precision/Recall:**
- `favor_precision=True` - focus on central/relevant elements
- `favor_recall=True` - include more elements
- `prune_xpath` - XPath expressions to exclude elements

**Performance:**
- `no_fallback=True` (deprecated, use `fast=True`) - bypasses fallback algorithms, ~2x faster
- `include_comments=False, include_tables=False, no_fallback=True` - fastest combination

**Metadata:**
- `with_metadata=True` - include metadata in output
- `only_with_metadata=True` - only output documents with essential metadata

**Language:**
- `target_language="de"` - filters by ISO 639-1 code (requires py3langid)

## Extractor Class (v1.9+)

```python
from trafilatura.settings import Extractor
options = Extractor(output_format="json", with_metadata=True)
options.formatting = True  # same as include_formatting
extract(my_doc, options=options)
```

## Date Extraction Parameters

Pass via `date_extraction_params` dict:
- `extensive_search` (bool) - more heuristics
- `original_date` (bool) - look for original publication date
- `outputformat` (string) - custom datetime format
- `max_date` (string, YYYY-MM-DD) - latest acceptable date

## Input Types

- Raw HTML strings
- LXML objects: `html.fromstring(my_doc)`
- Raw HTTP responses: `fetch_response()` then `bare_extraction(response.data, url=response.url)`
- BeautifulSoup: convert via `from lxml.html.soupparser import convert_tree`

## Navigation Functions

**Feeds:**
```python
from trafilatura import feeds
feeds.find_feed_urls('https://example.com/', target_lang='en')
```

**Sitemaps:**
```python
from trafilatura import sitemaps
sitemaps.sitemap_search('https://example.com/', target_lang='en')
```

## Readability Check

```python
from trafilatura.readability_lxml import is_probably_readerable
is_probably_readerable(html)
```

## Memory Management

```python
from trafilatura.meta import reset_caches
reset_caches()  # release RAM from cached data
```

## Key Deprecations

- `process_record()` -> use `extract()`
- `csv_output`, `json_output`, `tei_output`, `xml_output` -> use `output_format`
- `no_fallback` -> use `fast`
- `bare_extraction(as_dict=True)` -> returns `Document` object, use `.as_dict()`