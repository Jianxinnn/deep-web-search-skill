from __future__ import annotations

import json
import urllib.request
from typing import Any


def fetch_text(url: str, timeout: int = 20, headers: dict[str, str] | None = None, data: bytes | None = None) -> str:
    request_headers = {"User-Agent": "deep-web-search-skill/0.1"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=data, headers=request_headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_json(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    return json.loads(fetch_text(url, timeout=timeout, headers=headers))


def post_json(url: str, payload: dict[str, Any], timeout: int = 30) -> Any:
    data = json.dumps(payload).encode("utf-8")
    return json.loads(fetch_text(url, timeout=timeout, headers={"Content-Type": "application/json"}, data=data))
