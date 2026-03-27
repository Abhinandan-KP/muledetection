"""
cycle_detector.py – Detect circular fund routing (money-mule rings).

Strategy
--------
Use NetworkX simple_cycles with an early-exit guard.
Canonical deduplication: a cycle [A,B,C] and [B,C,A] are the same ring;
we normalise by rotating to the lexicographically smallest node first,
then using a frozenset key for O(1) dedup.

Performance
-----------
• Hard cap of MAX_CYCLES to prevent exponential blowup on dense graphs.
• Optional timeout via threading (disabled on PyPy-incompatible platforms).
"""
from __future__ import annotations

import logging
import threading
from typing import List, Dict

import networkx as nx

from .config import CYCLE_MIN_LEN, CYCLE_MAX_LEN, MAX_CYCLES, CYCLE_TIMEOUT_SECONDS

log = logging.getLogger(__name__)


def _canonical_cycle(cycle: list) -> tuple:
    """
    Rotate cycle so the lexicographically smallest node is first.
    Returns a tuple for use as a dict key.
    """
    if not cycle:
        return tuple(cycle)
    min_idx = cycle.index(min(cycle))
    rotated = cycle[min_idx:] + cycle[:min_idx]
    return tuple(rotated)


def detect_cycles(G: nx.DiGraph) -> List[Dict]:
    """
    Detect simple directed cycles of length CYCLE_MIN_LEN to CYCLE_MAX_LEN.

    Returns
    -------
    List of ring dicts with keys:
        members       : list[str]   – ordered account IDs in the cycle
        pattern       : str         – e.g. "cycle_length_3"
        cycle_length  : int
    """
    rings: List[Dict] = []
    seen: set = set()
    cycle_count = 0
    timed_out = False

    # ── SCC pre-filter ──────────────────────────────────────────────────────────
    # Cycles can only exist within strongly-connected components of size ≥ CYCLE_MIN_LEN.
    # Building a subgraph of just those nodes before calling simple_cycles avoids
    # iterating over the (often large) acyclic majority of the graph.
    # Re-use precomputed SCCs from build_graph if available (avoids a duplicate
    # O(V+E) pass on every request).
    sccs = G.graph.get("_sccs") or list(nx.strongly_connected_components(G))
    scc_nodes: set = set()
    for scc in sccs:
        if len(scc) >= CYCLE_MIN_LEN:
            scc_nodes.update(scc)

    if not scc_nodes:
        log.info("Cycle detection: 0 rings found (no qualifying SCCs)")
        return rings

    H = G.subgraph(scc_nodes)  # O(1) view — no copy
    log.info(
        "Cycle detection: SCC subgraph has %d nodes / %d total (%.1f%% reduction)",
        len(scc_nodes),
        G.number_of_nodes(),
        100.0 * (1 - len(scc_nodes) / G.number_of_nodes()) if G.number_of_nodes() else 0,
    )

    # ── Threading-based timeout ─────────────────────────────────────────────────
    stop_event = threading.Event()

    def _timeout_setter():
        stop_event.set()

    timer = threading.Timer(CYCLE_TIMEOUT_SECONDS, _timeout_setter)
    timer.daemon = True
    timer.start()

    try:
        for cycle in nx.simple_cycles(H):
            if stop_event.is_set():
                timed_out = True
                log.warning(
                    "Cycle detection timed out after %.1fs; found %d cycles so far.",
                    CYCLE_TIMEOUT_SECONDS,
                    cycle_count,
                )
                break
            if cycle_count >= MAX_CYCLES:
                log.warning("Cycle cap (%d) reached; stopping early.", MAX_CYCLES)
                break

            length = len(cycle)
            if length < CYCLE_MIN_LEN or length > CYCLE_MAX_LEN:
                continue

            key = _canonical_cycle(cycle)
            if key in seen:
                continue
            seen.add(key)

            rings.append({
                "members": list(key),      # canonical ordering
                "pattern": f"cycle_length_{length}",
                "cycle_length": length,
            })
            cycle_count += 1

    except Exception as exc:
        log.error("Cycle detection error: %s", exc)
    finally:
        timer.cancel()

    log.info(
        "Cycle detection: %d rings found%s",
        len(rings),
        " (timed out)" if timed_out else "",
    )
    return rings
