"""TravelMind Stage 12: Wikimedia destination background information.

Offline by default. Live calls are explicit, one request maximum per invocation.
Wikimedia community content is NOT an official source for ticket prices/hours.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
import os
import re
from urllib.parse import quote, urlparse

import requests

# Titles are deliberately explicit to avoid ambiguous pages in student tests.
CITY_TITLES = {
    "xi'an": "Xi'an", "xian": "Xi'an", "西安": "Xi'an", "西安市": "Xi'an",
    "beijing": "Beijing", "北京": "Beijing", "北京市": "Beijing",
    "shanghai": "Shanghai", "上海": "Shanghai", "上海市": "Shanghai",
    "chengdu": "Chengdu", "成都": "Chengdu", "成都市": "Chengdu",
    "hangzhou": "Hangzhou", "杭州": "Hangzhou", "杭州市": "Hangzhou",
}

# These are generated fixture descriptions only, deliberately not presented as retrieved facts.
DEMO_SUMMARY = "[SYNTHETIC] Sample city history and culture paragraph used solely to test the adapter."


class IntroParser(HTMLParser):
    """Best-effort extraction of brief prose from an HTML travel guide.

    No extraction of changing ticket prices or official opening hours.  This
    parser is intentionally conservative and stops before major headings.
    """
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_p = False
        self.skip_level = 0
        self.done = False
        self.parts = []
        self.paragraph = []
        self.ignored = {"script", "style", "nav", "table", "figure", "aside"}

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        if tag in self.ignored:
            self.skip_level += 1
        if tag in {"h2", "h3"} and self.parts:
            self.done = True
        if tag == "p" and self.skip_level == 0:
            self.in_p = True
            self.paragraph = []

    def handle_endtag(self, tag):
        if tag == "p" and self.in_p:
            cleaned = " ".join("".join(self.paragraph).split())
            if len(cleaned) >= 35:
                self.parts.append(cleaned)
            self.in_p = False
            self.paragraph = []
        if tag in self.ignored and self.skip_level:
            self.skip_level -= 1

    def handle_data(self, data):
        if self.in_p and not self.skip_level and not self.done:
            self.paragraph.append(data)


def clean_text(raw: str, limit: int = 850) -> str:
    text = " ".join(str(raw or "").split())
    if len(text) > limit:
        truncated = text[:limit]
        text = truncated.rsplit(" ", 1)[0] + "…" if " " in truncated else truncated + "…"
    return text


def title_for(city: str) -> str:
    city_key = city.strip().casefold().replace("’", "'")
    if city_key not in CITY_TITLES:
        raise ValueError("This Stage 12 demo supports Xi'an, Beijing, Shanghai, Chengdu, Hangzhou. Add verified title mappings for more cities.")
    return CITY_TITLES[city_key]


def contact_user_agent(contact: str) -> str:
    """Wikimedia requires identifiable client UA, never use fake details."""
    contact = (contact or "").strip()
    good_url = contact.startswith("https://") and bool(urlparse(contact).hostname)
    good_email = bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", contact))
    if not (good_url or good_email):
        raise ValueError("Live Wikimedia requests need TRAVELMIND_WIKIMEDIA_CONTACT: your real email or project URL (HTTPS).")
    return f"TravelMindStudentProject/0.1 ({contact}) PythonRequests"


def _source_record(source: str, title: str, retrieved_at: str | None, *, revision=None, published_at=None):
    host = "en.wikipedia.org" if source == "wikipedia" else "en.wikivoyage.org"
    return {
        "provider": source,
        "page_url": f"https://{host}/wiki/{quote(title.replace(' ', '_'), safe='')}",
        "retrieved_at": retrieved_at,
        "revision": revision,
        "page_modified_at": published_at,
        "license": "CC BY-SA 4.0 (check any page-specific third-party media separately)",
        "attribution_required": True,
        "source_type": "community_edited_not_official",
    }


def fetch_background(city: str, source: str = "wikipedia", live: bool = False,
                     *, contact: str | None = None, http_get=None) -> dict:
    """Fetch at most one page. Never follow redirects to arbitrary non-Wikimedia hosts.

    Use mocked http_get for tests only. No client-side caching or silent retries.
    """
    if source not in {"wikipedia", "wikivoyage"}:
        raise ValueError("source must be wikipedia or wikivoyage")
    title = title_for(city)
    result = {
        "schema_version": "1.1-draft",
        "component": "destination_content_adapter",
        "mode": "live_wikimedia_transient" if live else "offline_synthetic",
        "request": {"city": city, "title": title, "source": source},
        "content": {
            "title": title,
            "language": "en",
            "summary": DEMO_SUMMARY if not live else None,
            "status": "simulated_not_verified" if not live else "unavailable",
            "information_type": "destination_background_only",
            "opening_hours_verified": False,
            "ticket_price_verified": False,
            "source": _source_record(source, title, None),
        },
        "trace": [],
        "warnings": ["Wikimedia text is community-edited background information, not an authoritative real-time booking or opening-hours feed."],
        "usage": {"wikimedia_requests_attempted": 0, "amap_requests_attempted": 0,
                  "baidu_requests_attempted": 0, "llm_requests_attempted": 0, "llm_tokens": 0},
    }
    if not live:
        result["trace"].append({"step": "offline_fixture", "external_requests": 0})
        result["warnings"].append("This paragraph is synthetic demonstration text, not retrieved from a website.")
        return result

    # Validate agent identity BEFORE making even one request.
    ua = contact_user_agent(contact if contact is not None else os.getenv("TRAVELMIND_WIKIMEDIA_CONTACT", ""))
    encoded = quote(title.replace(" ", "_"), safe="")
    if source == "wikipedia":
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    else:
        url = f"https://en.wikivoyage.org/w/rest.php/v1/page/{encoded}/html"
    requester = http_get or requests.get
    result["usage"]["wikimedia_requests_attempted"] = 1
    result["trace"].append({"step": f"fetch_{source}_page", "external_requests": 1})
    try:
        response = requester(url, headers={"User-Agent": ua, "Accept": "application/json" if source == "wikipedia" else "text/html"},
                             timeout=15, allow_redirects=False)
        if response.status_code in {429, 503}:
            result["warnings"].append("Provider rate-limited or unavailable; no automatic retry. Respect Retry-After.")
            return result
        if 300 <= response.status_code < 400:
            result["content"]["status"] = "redirect_not_followed"
            result["warnings"].append("Provider redirected to another page; this cost-controlled adapter does not auto-follow redirects.")
            return result
        if response.status_code == 404:
            result["content"]["status"] = "page_not_found"
            return result
        response.raise_for_status()
        # No redirects: avoid silent extra requests and untrusted destinations.
        if source == "wikipedia":
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Unexpected Wikipedia JSON")
            summary = clean_text(data.get("extract", ""))
            title_returned = data.get("title") or title
            revision = data.get("revision")
            modified_at = data.get("timestamp")
        else:
            html = response.text
            if len(html) > 3_000_000:
                raise ValueError("Wikivoyage page too large for this demo")
            parser = IntroParser()
            parser.feed(html)
            summary = clean_text(" ".join(parser.parts[:3]))
            title_returned = title
            revision = None
            modified_at = None
        result["content"].update({
            "title": title_returned,
            "summary": summary or None,
            "status": "community_content_retrieved" if summary else "no_extractable_summary",
            "source": _source_record(source, title_returned,
                                     datetime.now(timezone.utc).isoformat(),
                                     revision=revision, published_at=modified_at)
        })
    except (requests.RequestException, ValueError, KeyError, TypeError) as error:
        # Never print URL with API key (there is no key), never mislabel failure as success.
        result["warnings"].append(f"Could not retrieve or parse {source} content: {type(error).__name__}.")
    return result


def main():
    parser = argparse.ArgumentParser(description="TravelMind Stage 12 destination descriptions")
    parser.add_argument("--city", default="Xi'an", help="Supported city name")
    parser.add_argument("--source", choices=["wikipedia", "wikivoyage"], default="wikipedia")
    parser.add_argument("--live", action="store_true", help="Allow one Wikimedia HTTP request")
    args = parser.parse_args()
    result = fetch_background(args.city, source=args.source, live=args.live)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
