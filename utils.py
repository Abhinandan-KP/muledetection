"""
utils.py – Ring merging & ID assignment utilities.

Ring merging
------------
If two rings (detected by different algorithms) share enough member accounts
we merge them into a single ring to avoid double-counting.
Threshold: >= 50 % of the smaller ring’s members overlap with the larger ring.
"""
from __future__ import annotations

import logging
from typing import List, Dict

log = logging.getLogger(__name__)

_MERGE_OVERLAP_RATIO = 0.5   # merge if ≥ 50 % of smaller ring overlaps


def _should_merge(ring_a: Dict, ring_b: Dict) -> bool:
    """Return True if the two rings share enough members to be considered the same ring."""
    set_a = set(ring_a["members"])
    set_b = set(ring_b["members"])
    overlap = len(set_a & set_b)
    smaller = min(len(set_a), len(set_b))
    if smaller == 0:
        return False
    return (overlap / smaller) >= _MERGE_OVERLAP_RATIO


def _merge_rings(rings: List[Dict]) -> List[Dict]:
    """
    Merge overlapping rings into unified rings.
    Uses a simple union-find-like greedy merge.
    """
    if not rings:
        return rings

    merged: List[Dict] = []
    used = [False] * len(rings)

    for i, ring_i in enumerate(rings):
        if used[i]:
            continue
        current = dict(ring_i)
        current_members = set(ring_i["members"])
        current_patterns = {ring_i["pattern"]}

        for j in range(i + 1, len(rings)):
            if used[j]:
                continue
            ring_j = rings[j]
            if _should_merge(current, ring_j):
                current_members |= set(ring_j["members"])
                current_patterns.add(ring_j["pattern"])
                used[j] = True

        current["members"] = sorted(current_members)
        # Keep the highest-priority pattern name as primary pattern
        _priority = [
            "cycle_length_3", "cycle_length_4", "cycle_length_5",
            "fan_in", "fan_out", "round_trip", "shell_chain",
        ]
        for p in _priority:
            if p in current_patterns:
                current["pattern"] = p
                break
        current["merged_patterns"] = sorted(current_patterns)
        merged.append(current)
        used[i] = True

    log.info("Ring merge: %d → %d rings", len(rings), len(merged))
    return merged


def assign_ring_ids(
    cycle_rings: List[Dict],
    smurf_rings: List[Dict],
    shell_rings: List[Dict],
    roundtrip_rings: List[Dict] | None = None,
    merge: bool = True,
) -> List[Dict]:
    """
    Combine all ring lists, optionally merge overlapping rings, then assign
    sequential RING_001, RING_002, … IDs.

    Returns a flat list with ring_id injected into each ring dict.
    """
    # Combine in priority order: cycles first (highest confidence)
    combined = cycle_rings + smurf_rings + shell_rings + (roundtrip_rings or [])

    if merge:
        combined = _merge_rings(combined)

    for i, ring in enumerate(combined, start=1):
        ring["ring_id"] = f"RING_{i:03d}"

    return combined
