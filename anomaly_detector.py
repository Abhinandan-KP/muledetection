"""
anomaly_detector.py – Detect statistical amount anomalies per account.

Flags accounts whose individual transactions deviate >N standard deviations
from their own mean transaction amount. Accounts with too few transactions
(< 5) are skipped to avoid noisy outlier detection.
"""
from __future__ import annotations

import logging
from typing import Dict, Set

import pandas as pd

from .config import AMOUNT_ANOMALY_STDDEV

log = logging.getLogger(__name__)

_MIN_TX_FOR_ANOMALY = 5  # need enough data for meaningful stats


def detect_amount_anomalies(df: pd.DataFrame) -> Set[str]:
    """
    Return account IDs that have at least one transaction whose amount is
    more than AMOUNT_ANOMALY_STDDEV standard deviations from that account's
    mean transaction size.

    Both sending and receiving sides are checked independently.
    Fully vectorised — no Python-level groupby for-loops.
    """
    flagged: Set[str] = set()

    if df.empty:
        return flagged

    for acc_col in ("sender_id", "receiver_id"):
        # Vectorised per-account stats in one groupby call
        stats = df.groupby(acc_col)["amount"].agg(
            mean_amt="mean",
            std_amt="std",     # pandas default ddof=1
            count_amt="count",
        )
        # Only accounts with enough data and non-zero std
        stats = stats[(stats["count_amt"] >= _MIN_TX_FOR_ANOMALY) & (stats["std_amt"] > 0)]

        if stats.empty:
            continue

        # Merge stats back onto transactions and compute z-scores in one shot
        merged = df[[acc_col, "amount"]].merge(
            stats[["mean_amt", "std_amt"]].reset_index(),
            on=acc_col,
        )
        merged["z"] = (merged["amount"] - merged["mean_amt"]).abs() / merged["std_amt"]
        flagged.update(merged.loc[merged["z"] > AMOUNT_ANOMALY_STDDEV, acc_col].unique())

    log.info("Amount anomaly detection: %d accounts flagged", len(flagged))
    return flagged
