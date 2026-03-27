"""
graph_builder.py – Build a labelled directed graph from transaction data.
Uses vectorised pandas operations for fast execution on large datasets.
"""
from __future__ import annotations

import logging

import networkx as nx
import pandas as pd

log = logging.getLogger(__name__)


def build_graph(df: pd.DataFrame, include_transactions: bool = True) -> nx.DiGraph:
    """
    Construct a directed weighted graph from a validated transaction DataFrame.

    Node attributes
    ---------------
    total_sent, total_received, net_flow : float
    tx_count, sent_count, received_count : int
    avg_sent, avg_received               : float
    unique_counterparties                : int
    first_tx, last_tx                    : str

    Edge attributes
    ---------------
    total_amount, avg_amount : float
    tx_count                 : int
    first_tx, last_tx        : str
    transactions             : list[dict]
    """
    G = nx.DiGraph()

    # ── Vectorised node statistics ─────────────────────────────────────────────
    # Compute all sender/receiver stats in two aggregation calls instead of many.
    sent_stats = df.groupby("sender_id").agg(
        total_sent=("amount", "sum"),
        sent_count=("amount", "count"),
        avg_sent=("amount", "mean"),
        sent_cp=("receiver_id", "nunique"),
        sent_first=("timestamp", "min"),
        sent_last=("timestamp", "max"),
    )
    recv_stats = df.groupby("receiver_id").agg(
        total_received=("amount", "sum"),
        received_count=("amount", "count"),
        avg_received=("amount", "mean"),
        recv_cp=("sender_id", "nunique"),
        recv_first=("timestamp", "min"),
        recv_last=("timestamp", "max"),
    )

    all_accounts = pd.Index(
        set(df["sender_id"].unique()) | set(df["receiver_id"].unique())
    )
    s = sent_stats.reindex(all_accounts)
    r = recv_stats.reindex(all_accounts)

    # Compute first/last timestamps across both sent and received in one pass
    # by stacking the two timestamp columns and taking min/max.
    first_ts = pd.concat([s["sent_first"], r["recv_first"]], axis=1).min(axis=1)
    last_ts  = pd.concat([s["sent_last"],  r["recv_last"]],  axis=1).max(axis=1)

    # Build node attribute DataFrame — all vectorised, no Python loop per account.
    node_df = pd.DataFrame({
        "total_sent":           s["total_sent"].fillna(0.0).round(2),
        "total_received":       r["total_received"].fillna(0.0).round(2),
        "sent_count":           s["sent_count"].fillna(0).astype(int),
        "received_count":       r["received_count"].fillna(0).astype(int),
        "avg_sent":             s["avg_sent"].fillna(0.0).round(2),
        "avg_received":         r["avg_received"].fillna(0.0).round(2),
        "sent_cp":              s["sent_cp"].fillna(0).astype(int),
        "recv_cp":              r["recv_cp"].fillna(0).astype(int),
        "first_tx":             first_ts.fillna("").astype(str),
        "last_tx":              last_ts.fillna("").astype(str),
    }, index=all_accounts)
    node_df["tx_count"]              = node_df["sent_count"] + node_df["received_count"]
    node_df["net_flow"]              = (node_df["total_received"] - node_df["total_sent"]).round(2)
    node_df["unique_counterparties"] = node_df["sent_cp"] + node_df["recv_cp"]

    # Add all nodes in a single batch call using itertuples (much faster than
    # per-node G.add_node() inside a loop with Series.get() lookups).
    G.add_nodes_from([
        (row.Index, {
            "total_sent":            row.total_sent,
            "total_received":        row.total_received,
            "net_flow":              row.net_flow,
            "tx_count":              row.tx_count,
            "sent_count":            row.sent_count,
            "received_count":        row.received_count,
            "avg_sent":              row.avg_sent,
            "avg_received":          row.avg_received,
            "unique_counterparties": row.unique_counterparties,
            "first_tx":              row.first_tx,
            "last_tx":               row.last_tx,
        })
        for row in node_df.itertuples()
    ])

    # ── Edges ──────────────────────────────────────────────────────────────────
    # Edge-level aggregate stats — vectorised groupby, no Python row loop.
    edge_stats = df.groupby(["sender_id", "receiver_id"]).agg(
        total_amount=("amount", "sum"),
        avg_amount=("amount", "mean"),
        tx_count=("amount", "count"),
        first_tx=("timestamp", "min"),
        last_tx=("timestamp", "max"),
    ).reset_index()

    # Build per-edge transaction lists only when graph detail is needed
    # (i.e. the frontend requested detail=true for graph visualisation).
    # On 10k-row datasets this Python loop takes ~0.5-1s on slow CPUs — skip it
    # when the caller only needs detection results.
    if include_transactions:
        df_sorted = df.sort_values("timestamp")
        tx_by_edge: dict[tuple, list] = {}
        for row in df_sorted[
            ["transaction_id", "amount", "timestamp", "sender_id", "receiver_id"]
        ].itertuples(index=False):
            key = (row.sender_id, row.receiver_id)
            if key not in tx_by_edge:
                tx_by_edge[key] = []
            tx_by_edge[key].append({
                "transaction_id": row.transaction_id,
                "amount":         round(float(row.amount), 2),
                "timestamp":      str(row.timestamp),
            })
    else:
        tx_by_edge = {}

    G.add_edges_from([
        (row.sender_id, row.receiver_id, {
            "total_amount": round(float(row.total_amount), 2),
            "avg_amount":   round(float(row.avg_amount), 2),
            "tx_count":     int(row.tx_count),
            "first_tx":     str(row.first_tx),
            "last_tx":      str(row.last_tx),
            "transactions": tx_by_edge.get((row.sender_id, row.receiver_id), []),
        })
        for row in edge_stats.itertuples(index=False)
    ])

    # ── Precompute SCCs once ────────────────────────────────────────────────────
    # Both cycle_detector and shell_detector need SCCs. Computing here once
    # (O(V+E)) and caching avoids a duplicate pass on every request.
    G.graph["_sccs"] = list(nx.strongly_connected_components(G))

    log.info("Graph built: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G
