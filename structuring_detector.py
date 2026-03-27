"""
structuring_detector.py – Detect amount structuring (sub-threshold transactions).

Structuring (also called "smurfing by amount") is when a launderer breaks a
single large transfer into multiple smaller transfers that each fall just
below a regulatory reporting threshold (commonly $10,000 for CTRs in the US).

This detector flags accounts that have multiple outgoing transactions whose
amounts are just below the threshold (within STRUCTURING_MARGIN %).
"""
from __future__ import annotations

import logging
from typing import Dict, Set

import pandas as pd

from .config import (
    STRUCTURING_THRESHOLD,
    STRUCTURING_MARGIN,
    STRUCTURING_MIN_TX,
)

log = logging.getLogger(__name__)


def detect_structuring(df: pd.DataFrame) -> Dict[str, Dict]:
    """
    Detect accounts with suspicious sub-threshold transaction patterns.

    Returns
    -------
    dict mapping account_id to:
        structured_tx_count : int   – number of transactions just below threshold
        avg_amount          : float – average amount of those transactions
    """
    flagged: Dict[str, Dict] = {}

    if df.empty:
        return flagged

    lower_bound = STRUCTURING_THRESHOLD * (1.0 - STRUCTURING_MARGIN)

    # Find transactions in the suspicious band: [lower_bound, threshold)
    mask = (df["amount"] >= lower_bound) & (df["amount"] < STRUCTURING_THRESHOLD)
    suspicious_tx = df[mask]

    if suspicious_tx.empty:
        return flagged

    # Group by sender — structuring is about how you SEND money
    for sender, grp in suspicious_tx.groupby("sender_id"):
        count = len(grp)
        if count >= STRUCTURING_MIN_TX:
            flagged[sender] = {
                "structured_tx_count": count,
                "avg_amount": round(float(grp["amount"].mean()), 2),
                "total_structured": round(float(grp["amount"].sum()), 2),
            }

    log.info("Structuring detection: %d accounts flagged", len(flagged))
    return flagged
