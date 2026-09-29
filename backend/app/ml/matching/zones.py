"""Walking-graph distance between campus zones (hops), from config/campus/zone_graph.json."""
from __future__ import annotations

import json
from collections import deque
from functools import lru_cache
from pathlib import Path

from ...config import ROOT

DEFAULT_HOPS = 3  # unknown zone pair: assume "a few zones apart"


@lru_cache
def _graph(path: str | None = None) -> dict[str, set[str]]:
    p = Path(path) if path else ROOT / "config" / "campus" / "zone_graph.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    adj: dict[str, set[str]] = {n: set() for n in data.get("nodes", [])}
    for a, b, *_ in data.get("edges", []):
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    return adj


def hops(a: str, b: str, graph: dict[str, set[str]] | None = None) -> int:
    if a == b:
        return 0
    g = graph if graph is not None else _graph()
    if a not in g or b not in g:
        return DEFAULT_HOPS
    seen, q = {a}, deque([(a, 0)])
    while q:
        node, d = q.popleft()
        for nxt in g[node]:
            if nxt == b:
                return d + 1
            if nxt not in seen:
                seen.add(nxt)
                q.append((nxt, d + 1))
    return DEFAULT_HOPS + 3  # disconnected


def reload() -> None:
    _graph.cache_clear()
