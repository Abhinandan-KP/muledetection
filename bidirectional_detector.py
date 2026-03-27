"""
bidirectional_detector.py – Detect round-trip (bi-directional) fund flows.

Flags account pairs where A→B and B→A both exist with similar total amounts.
This catches 2-node laundering cycles that the main cycle detector skips
(minimum cycle length = 3).

A tolerance parameter controls how similar the amounts must be (default 20%).
"""
from __future__ import annotations

import logging
from typing import List, Dict

import networkx as nx

from .config import ROUND_TRIP_AMOUNT_TOLERANCE

log = logging.getLogger(__name__)


def detect_round_trips(G: nx.DiGraph) -> List[Dict]:
    """
    Detect bi-directional edges where flow in both directions is similar.

    Returns ring dicts with pattern = "round_trip".
    """
    rings: List[Dict] = []
    seen: set = set()

    for u, v, attrs in G.edges(data=True):
        if G.has_edge(v, u):
            key = tuple(sorted([u, v]))
            if key in seen:
                continue
            seen.add(key)

            fwd_amount = attrs.get("total_amount", 0.0)
            rev_amount = G[v][u].get("total_amount", 0.0)

            if fwd_amount <= 0 or rev_amount <= 0:
                continue

            # Check if amounts are within tolerance of each other
            larger = max(fwd_amount, rev_amount)
            smaller = min(fwd_amount, rev_amount)
            diff_ratio = (larger - smaller) / larger

            if diff_ratio <= ROUND_TRIP_AMOUNT_TOLERANCE:
                rings.append({
                    "members": sorted([u, v]),
                    "pattern": "round_trip",
                    "forward_amount": fwd_amount,
                    "reverse_amount": rev_amount,
                    "similarity": round(1.0 - diff_ratio, 3),
                })

    log.info("Round-trip detection: %d pairs found", len(rings))
    return rings
