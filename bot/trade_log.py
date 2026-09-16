"""CSV trade logging -- read later by the Cowork reporting layer via Drive sync."""
import csv
import os
from datetime import datetime, timezone

import config

FIELDS = [
    "timestamp_utc",
    "symbol",
    "action",       # buy / sell / exit
    "quantity",
    "price",
    "commission",
    "stop_price",
    "strategy",     # mean_reversion / trend_following
    "regime",       # ranging / trending
    "equity_after",
    "realized_pnl",  # only populated on exit rows -- matches backtest/engine.py's Fill schema
]


def _ensure_header(path: str) -> None:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=FIELDS).writeheader()


def log_trade(**fields) -> None:
    path = config.TRADE_LOG_PATH
    _ensure_header(path)
    fields.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
    with open(path, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writerow(fields)
