from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse
from urllib.request import urlopen

import yaml

DEFAULT_COLLECTION_URL = (
    "https://raw.githubusercontent.com/dodobrands/"
    "dodo-api-postman-collection/main/dodo-is-api-postman-collection.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate disabled Dodo tool candidates from Postman.")
    parser.add_argument("--input", default=DEFAULT_COLLECTION_URL, help="Postman JSON path or URL.")
    parser.add_argument("--output", default="configs/dodo.generated.yaml", help="Output YAML path.")
    args = parser.parse_args()

    collection = load_json(args.input)
    tools = []
    for item in walk_items(collection.get("item", [])):
        request = item["request"]
        method = request.get("method", "GET").upper()
        raw_url = request.get("url", {}).get("raw") if isinstance(request.get("url"), dict) else None
        if not raw_url:
            continue
        path, query_params = normalize_url(raw_url)
        tools.append(
            {
                "name": make_tool_name(method, path),
                "description": item["name"],
                "connector": "dodo",
                "method": method,
                "path": path,
                "risk_level": "read" if method == "GET" else "write",
                "enabled": False,
                "requires_approval": method != "GET",
                "allowed_query_params": query_params,
                "max_response_chars": 30000,
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(yaml.safe_dump({"tools": tools}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"Wrote {len(tools)} tool candidates to {output}")
    return 0


def load_json(source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        with urlopen(source, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def walk_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for item in items:
        if "request" in item:
            found.append(item)
        found.extend(walk_items(item.get("item", [])))
    return found


def normalize_url(raw_url: str) -> tuple[str, list[str]]:
    raw_url = raw_url.replace("{{api_url}}", "https://api.dodois.io")
    raw_url = raw_url.replace("{{country}}", "{country}")
    parsed = urlparse(raw_url)
    path = parsed.path
    query_params = [key for key, _value in parse_qsl(parsed.query, keep_blank_values=True)]
    path = re.sub(r"<[^>]+>", "{id}", path)
    return path, sorted(set(query_params))


def make_tool_name(method: str, path: str) -> str:
    parts = [part for part in path.split("/") if part and part not in {"dodopizza", "{country}"}]
    cleaned = [re.sub(r"[^a-zA-Z0-9]+", "_", part).strip("_").lower() for part in parts]
    cleaned = [part for part in cleaned if part and part != "id"]
    stem = "_".join(cleaned[-4:] or ["endpoint"])
    return f"dodo_{method.lower()}_{stem}"


if __name__ == "__main__":
    sys.exit(main())

