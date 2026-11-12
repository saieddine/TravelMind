"""Stage 9 — bounded, opt-in retrieval from pre-reviewed official attraction pages.

No Amap/Baidu/LLM calls. No network unless an explicit caller invokes fetch_official.
A live run may issue at most one robots.txt request and one HTML request.
No page content or retrieved map records are written to disk.
"""
from __future__ import annotations

import json
from pathlib import Path
from providers.config import RESOURCE_ROOT
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

REGISTRY = RESOURCE_ROOT / "official_source_registry.json"
USER_AGENT = "TravelMindStudentResearch/0.1"
MAX_BYTES = 450_000


class OfficialSourceError(RuntimeError):
    pass


def load_registry(path: Path = REGISTRY) -> dict[str, dict]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(registry, list):
        raise ValueError("Official registry must be a JSON list")
    result = {}
    for item in registry:
        identifier = item["source_id"]
        parsed = urlsplit(item["url"])
        if (not parsed.scheme == "https" or parsed.username or parsed.password
                or not parsed.hostname or parsed.port not in (None, 443)):
            raise ValueError("Only reviewed HTTPS URLs may be used")
        if identifier in result:
            raise ValueError("Duplicate source_id")
        result[identifier] = item
    return result


def _get_checked(get, url: str, *, max_bytes: int) -> bytes:
    try:
        response = get(
            url,
            timeout=12,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain"},
            allow_redirects=False,
            stream=True,
        )
        if 300 <= response.status_code < 400:
            raise OfficialSourceError("Official source redirected; review its new URL before fetching")
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        if not ("text/html" in content_type or "text/plain" in content_type):
            raise OfficialSourceError("The page is not HTML/plain text")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=16_384):
            content.extend(chunk)
            if len(content) > max_bytes:
                raise OfficialSourceError("Official page exceeds safety size limit")
        return bytes(content)
    except requests.RequestException as error:
        raise OfficialSourceError(f"Official page request failed: {type(error).__name__}") from None
    finally:
        if 'response' in locals():
            response.close()


def fetch_official(source_id: str, *, http_get=None) -> dict:
    """Explicit network operation. Fail closed if robots cannot be checked.

    Never receives arbitrary URLs from a trip request; uses only a reviewed registry.
    HTTP attempts: at most 2 (robots.txt + official HTML). No retries.
    """
    registry = load_registry()
    if source_id not in registry:
        raise ValueError("Unknown reviewed source_id; no request attempted")
    entry = registry[source_id]
    url = entry["url"]
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    get = http_get or requests.get
    attempts = 0
    try:
        attempts += 1
        robots_text = _get_checked(get, robots_url, max_bytes=80_000).decode("utf-8", "replace")
        robots = RobotFileParser()
        robots.parse(robots_text.splitlines())
        if not robots.can_fetch(USER_AGENT, url):
            return {"source": entry, "html": None, "http_attempts": attempts,
                    "status": "robots_disallow", "note": "No page requested"}
        attempts += 1
        raw = _get_checked(get, url, max_bytes=MAX_BYTES)
    except OfficialSourceError as exc:
        return {"source": entry, "html": None, "http_attempts": attempts,
                "status": "fetch_failed", "note": str(exc)}
    return {"source": entry, "html": raw.decode("utf-8", "replace"),
            "http_attempts": attempts, "status": "fetched"}
