"""
scoring.py – Suspicion scoring engine.

Scoring model
-------------
1. Pattern contributions  – per ring membership (configurable weights in config.py)
2. Multi-ring bonus       – extra points per additional ring an account belongs to
3. High-velocity bonus    – accounts transacting > HIGH_VELOCITY_TX_PER_DAY per day
4. Network centrality     – small bonus based on betweenness centrality (skipped
                             for large graphs to stay within 30-second budget)
5. Amount anomaly         – accounts with transactions >3 std dev from their mean
6. Round-trip             – bi-directional flows with similar amounts (2-node cycles)
7. Rapid movement         – accounts with very short receive-to-forward dwell times
8. Structuring            – accounts sending multiple amounts just below thresholds
9. Risk explanations      – human-readable explanation string per account

All scores are capped at 100.0 and returned sorted descending.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set

import networkx as nx
import pandas as pd

from .config import (
    SCORE_CYCLE_3, SCORE_CYCLE_4, SCORE_CYCLE_5,
    SCORE_FAN_IN, SCORE_FAN_OUT, SCORE_SHELL,
    SCORE_HIGH_VELOCITY, SCORE_MULTI_RING_BONUS, SCORE_CENTRALITY_MAX,
    HIGH_VELOCITY_TX_PER_DAY,
    SCORE_AMOUNT_ANOMALY, SCORE_ROUND_TRIP, SCORE_RAPID_MOVEMENT,
    SCORE_STRUCTURING,
    FAN_THRESHOLD,
)

log = logging.getLogger(__name__)

PATTERN_SCORES: Dict[str, float] = {
    "cycle_length_3": SCORE_CYCLE_3,
    "cycle_length_4": SCORE_CYCLE_4,
    "cycle_length_5": SCORE_CYCLE_5,
    "fan_in":         SCORE_FAN_IN,
    "fan_out":        SCORE_FAN_OUT,
    "shell_chain":    SCORE_SHELL,
    "round_trip":     SCORE_ROUND_TRIP,
}

# Graphs larger than this skip betweenness centrality (expensive)
_CENTRALITY_MAX_NODES = 500


def _velocity_accounts(df: pd.DataFrame) -> Set[str]:
    """Return account IDs whose average tx/day exceeds the threshold."""
    if df.empty:
        return set()
    span_days = max(
        (df["timestamp"].max() - df["timestamp"].min()).total_seconds() / 86400,
        1.0,
    )
    tx_counts = (
        pd.concat([
            df["sender_id"].value_counts(),
            df["receiver_id"].value_counts(),
        ])
        .groupby(level=0).sum()
    )
    per_day = tx_counts / span_days
    flagged = set(per_day[per_day > HIGH_VELOCITY_TX_PER_DAY].index)
    log.info("High-velocity accounts: %d", len(flagged))
    return flagged


def _centrality_scores(G: nx.DiGraph) -> Dict[str, float]:
    """
    Compute normalised betweenness centrality (0-1) for nodes.
    Returns empty dict if graph is too large to compute quickly.
    """
    if G.number_of_nodes() > _CENTRALITY_MAX_NODES:
        log.info("Graph too large for centrality computation; skipping.")
        return {}
    try:
        raw = nx.betweenness_centrality(G, normalized=True)
        return raw
    except Exception as exc:
        log.warning("Centrality computation failed: %s", exc)
        return {}


_PATTERN_EXPLANATIONS: Dict[str, str] = {
    "cycle_length_3": "Participates in a 3-node circular fund routing cycle",
    "cycle_length_4": "Participates in a 4-node circular fund routing cycle",
    "cycle_length_5": "Participates in a 5-node circular fund routing cycle",
    "fan_in": f"Receives from {FAN_THRESHOLD}+ unique senders within 72 hours (aggregator pattern)",
    "fan_out": f"Sends to {FAN_THRESHOLD}+ unique receivers within 72 hours (disperser pattern)",
    "shell_chain": "Part of a layered chain through low-activity shell accounts",
    "round_trip": "Bi-directional flow with similar amounts (possible round-tripping)",
    "amount_anomaly": "Transaction amounts deviate >3σ from account's mean",
    "rapid_movement": "Receives and forwards funds within minutes (pass-through)",
    "structuring": "Multiple transactions just below reporting threshold ($10K)",
    "high_velocity": "Unusually high transaction rate (>5 tx/day average)",
    "multi_ring": "Belongs to multiple distinct fraud rings",
}


def _build_risk_explanation(patterns: list, ring_ids: list, extra: dict) -> str:
    """Build a human-readable risk explanation for an account."""
    parts = []
    for p in patterns:
        explanation = _PATTERN_EXPLANATIONS.get(p)
        if explanation:
            parts.append(explanation)

    if len(ring_ids) > 1:
        parts.append(f"Connected to {len(ring_ids)} fraud rings: {', '.join(ring_ids)}")
    elif ring_ids:
        parts.append(f"Member of {ring_ids[0]}")

    if extra.get("min_dwell_minutes") is not None:
        parts.append(f"Fastest pass-through: {extra['min_dwell_minutes']} min")
    if extra.get("structured_tx_count"):
        parts.append(
            f"{extra['structured_tx_count']} transactions in ${extra.get('avg_amount', 0):,.0f} "
            f"range (just below $10K threshold)"
        )

    return ". ".join(parts) + "." if parts else ""


def calculate_scores(
    rings: List[Dict],
    df: pd.DataFrame,
    G: nx.DiGraph | None = None,
    anomaly_accounts: set | None = None,
    rapid_accounts: dict | None = None,
    structuring_accounts: dict | None = None,
) -> Dict[str, Dict]:
    """
    Build a per-account suspicion score map.

    Parameters
    ----------
    rings                : merged ring list with ring_id assigned
    df                   : transaction DataFrame
    G                    : NetworkX DiGraph (for centrality)
    anomaly_accounts     : set of account IDs with amount anomalies
    rapid_accounts       : dict mapping account_id → {min_dwell_minutes, rapid_count}
    structuring_accounts : dict mapping account_id → {structured_tx_count, avg_amount, ...}

    Returns
    -------
    dict mapping account_id to:
        score            : float      – 0–100, capped
        patterns         : list[str]  – unique detected pattern names
        ring_ids         : list[str]  – all ring IDs this account belongs to
        risk_explanation : str        – human-readable explanation
    """
    anomaly_accounts = anomaly_accounts or set()
    rapid_accounts = rapid_accounts or {}
    structuring_accounts = structuring_accounts or {}

    vel_accounts = _velocity_accounts(df)
    centrality   = _centrality_scores(G) if G is not None else {}
    data: Dict[str, Dict] = {}

    def _entry(acc: str) -> Dict:
        if acc not in data:
            data[acc] = {"score": 0.0, "patterns": set(), "ring_ids": [], "_extra": {}}
        return data[acc]

    # 1. Pattern contributions (ring-based)
    for ring in rings:
        ring_id    = ring["ring_id"]
        pattern    = ring["pattern"]
        base_score = PATTERN_SCORES.get(pattern, 10.0)
        hub        = ring.get("hub")  # set by smurf_detector for fan_in/fan_out
        # shell_intermediaries: only the pass-through nodes (not source/destination)
        shell_intermediaries = set(ring.get("shell_intermediaries", []))

        for acc in ring["members"]:
            e = _entry(acc)
            if ring_id not in e["ring_ids"]:
                e["ring_ids"].append(ring_id)
            # For fan patterns, only the hub (aggregator/disperser) receives the score
            # and pattern label. Spokes (employees, ordinary payers) are ring members
            # only — they are NOT independently suspicious.
            if pattern in ("fan_in", "fan_out"):
                if acc == hub:
                    e["score"] += base_score
                    e["patterns"].add(pattern)
            # For shell chains, ring members ARE the shell intermediaries (Option A).
            # Source and destination nodes are excluded from members entirely, so
            # every member here is a confirmed pass-through shell account.
            elif pattern == "shell_chain":
                e["score"] += base_score
                e["patterns"].add(pattern)
            else:
                e["score"] += base_score
                e["patterns"].add(pattern)

    # 2. Multi-ring bonus (account belongs to more than one ring)
    for acc, e in data.items():
        extra_rings = max(len(e["ring_ids"]) - 1, 0)
        if extra_rings > 0:
            e["score"] += SCORE_MULTI_RING_BONUS * extra_rings
            e["patterns"].add("multi_ring")

    # 3. High-velocity bonus
    for acc in vel_accounts:
        e = _entry(acc)
        e["score"] += SCORE_HIGH_VELOCITY
        e["patterns"].add("high_velocity")

    # 4. Network centrality bonus (up to SCORE_CENTRALITY_MAX points)
    if centrality:
        max_c = max(centrality.values()) if centrality else 1.0
        for acc, c_val in centrality.items():
            if acc in data:
                bonus = (c_val / max_c) * SCORE_CENTRALITY_MAX if max_c > 0 else 0
                data[acc]["score"] += bonus

    # 5. Amount anomaly bonus
    for acc in anomaly_accounts:
        e = _entry(acc)
        e["score"] += SCORE_AMOUNT_ANOMALY
        e["patterns"].add("amount_anomaly")

    # 6. Rapid movement bonus
    for acc, info in rapid_accounts.items():
        e = _entry(acc)
        e["score"] += SCORE_RAPID_MOVEMENT
        e["patterns"].add("rapid_movement")
        e["_extra"]["min_dwell_minutes"] = info.get("min_dwell_minutes")
        e["_extra"]["rapid_count"] = info.get("rapid_count")

    # 7. Structuring bonus
    for acc, info in structuring_accounts.items():
        e = _entry(acc)
        e["score"] += SCORE_STRUCTURING
        e["patterns"].add("structuring")
        e["_extra"]["structured_tx_count"] = info.get("structured_tx_count")
        e["_extra"]["avg_amount"] = info.get("avg_amount")

    # 8. Normalise and build explanations
    for acc, e in data.items():
        e["score"]    = float(min(round(e["score"], 1), 100.0))  # always a float
        e["patterns"] = sorted(e["patterns"])   # deterministic order
        e["risk_explanation"] = _build_risk_explanation(
            e["patterns"], e["ring_ids"], e.get("_extra", {})
        )
        del e["_extra"]  # internal only, not exposed

    log.info("Scoring complete: %d accounts scored", len(data))
    return data
