"""
shell_detector.py – Detect layered shell account networks.

Definition
----------
A shell chain is a directed path of length SHELL_MIN_CHAIN to SHELL_MAX_CHAIN
hops where ALL intermediate nodes (everything except source and destination)
are "pass-through shell" accounts — low-activity nodes used purely to add
layers of obfuscation.

Pass-through shell criteria
----------------------------
A node is a shell intermediary if ALL of the following hold:
  1. tx_count ≤ SHELL_MAX_TX  (very few transactions — kept dormant)
  2. in_degree > 0             (receives money)
  3. out_degree > 0            (forwards money — pure pass-through, not a dead end)
  4. NOT in any strongly-connected component of size > 1.
     Nodes in SCCs are participants in cycles, not pass-through shells.
     This prevents cycle nodes (A1→A2→A3→A1) from being misclassified as shells.

Source and destination nodes have no special tx_count requirements — they are
simply the first and last nodes of the discovered chain.

Algorithm
---------
Iterative DFS that starts from every node with at least one successor that
qualifies as a shell intermediary.  Explores through the shell subgraph and
terminates (potentially recording a chain) whenever it reaches a non-shell node
or exhausts extension depth.

Hard cap MAX_SHELL_CHAINS prevents excessive output.
"""
from __future__ import annotations

import logging
from typing import List, Dict

import networkx as nx

from .config import SHELL_MAX_TX, SHELL_MIN_CHAIN, SHELL_MAX_CHAIN, MAX_SHELL_CHAINS

log = logging.getLogger(__name__)


def detect_shell_networks(G: nx.DiGraph) -> List[Dict]:
    """
    Detect layered shell-account chains.

    Returns
    -------
    List of ring dicts with keys:
        members               : list[str]  – full path [source, shell1, ..., dest]
        pattern               : "shell_chain"
        chain_length          : int        – number of hops (edges)
        shell_intermediaries  : list[str]  – the low-tx pass-through accounts
    """
    rings: List[Dict] = []
    seen_paths: set = set()
    chain_count = 0

    # ── Identify pass-through shell nodes ─────────────────────────────────────
    # Nodes inside cycles share an SCC with other nodes — exclude them so that
    # cycle edges are never counted as "shell" layers.
    # Re-use precomputed SCCs from build_graph if available.
    sccs = G.graph.get("_sccs") or list(nx.strongly_connected_components(G))
    cycle_nodes: set = set()
    for component in sccs:
        if len(component) > 1:
            cycle_nodes.update(component)

    shell_nodes: set = {
        n for n, d in G.nodes(data=True)
        if d.get("tx_count", 0) <= SHELL_MAX_TX
        and G.in_degree(n) > 0
        and G.out_degree(n) > 0
        and n not in cycle_nodes
    }

    total_candidates = len([
        n for n, d in G.nodes(data=True)
        if d.get("tx_count", 0) <= SHELL_MAX_TX
    ])
    log.info(
        "Shell detection: %d shell candidates / %d total nodes (%d pass-through after SCC filter)",
        total_candidates,
        G.number_of_nodes(),
        len(shell_nodes),
    )

    if not shell_nodes:
        log.info("Shell detection: 0 chains found")
        return rings

    # ── Iterative DFS ─────────────────────────────────────────────────────────
    # Start from every node that has at least one shell successor.
    candidate_sources = [
        n for n in G.nodes()
        if any(nbr in shell_nodes for nbr in G.successors(n))
    ]

    for source in candidate_sources:
        if chain_count >= MAX_SHELL_CHAINS:
            log.warning("Shell chain cap (%d) reached.", MAX_SHELL_CHAINS)
            break

        # Stack: (current_path, visited_set)
        stack = [
            ([source, nbr], {source, nbr})
            for nbr in G.successors(source)
            if nbr in shell_nodes
        ]

        while stack and chain_count < MAX_SHELL_CHAINS:
            path, visited = stack.pop()
            current = path[-1]
            n_hops = len(path) - 1

            for nbr in G.successors(current):
                if nbr in visited:
                    continue

                new_path = path + [nbr]
                new_hops = n_hops + 1
                intermediaries = new_path[1:-1]  # nodes between source and nbr

                # Always check if we have a valid chain length and all intermediaries are shells
                if (
                    new_hops >= SHELL_MIN_CHAIN
                    and all(n in shell_nodes for n in intermediaries)
                ):
                    key = tuple(intermediaries)  # deduplicate by intermediary set
                    if key not in seen_paths:
                        seen_paths.add(key)
                        rings.append({
                            # members = only the shell intermediaries (Option A).
                            # Source and destination are NOT flagged as suspicious;
                            # they are entry/exit nodes, not the shell accounts.
                            "members": list(intermediaries),
                            "pattern": "shell_chain",
                            "chain_length": new_hops,
                            "shell_intermediaries": intermediaries,
                        })
                        chain_count += 1

                # Continue extending through shell nodes (up to depth limit)
                if nbr in shell_nodes and new_hops < SHELL_MAX_CHAIN:
                    stack.append((new_path, visited | {nbr}))

    log.info("Shell detection: %d chains found", len(rings))
    return rings

