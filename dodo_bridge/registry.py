from __future__ import annotations

from pathlib import Path

import yaml

from dodo_bridge.models import ToolSpec


class ToolRegistry:
    def __init__(self, path: Path):
        self.path = path
        self._tools = self._load(path)

    def _load(self, path: Path) -> dict[str, ToolSpec]:
        if not path.exists():
            raise FileNotFoundError(f"Tool registry not found: {path}")
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tools = payload.get("tools", [])
        parsed = [ToolSpec.model_validate(tool) for tool in tools]
        return {tool.name: tool for tool in parsed}

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

