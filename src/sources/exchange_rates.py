"""Exchange rates from open.er-api.com (free, no key, includes UAH).
Reports change against the previous run.
"""
import logging
import sys
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from .base import DataSource

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from state_store import StateStore

logger = logging.getLogger(__name__)

API_URL = "https://open.er-api.com/v6/latest/{base}"


def _clean_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw


def _smart_round(v: float) -> float:
    if v >= 100:
        return round(v, 2)
    if v >= 1:
        return round(v, 3)
    return round(v, 4)


class ExchangeRatesSource(DataSource):
    name = "exchange_rates"

    def fetch(self) -> list[dict]:
        base = self.config.get("base_currency", "USD")
        targets = self.config.get("target_currencies", ["EUR", "UAH", "GBP"])

        resp = requests.get(API_URL.format(base=base), timeout=10)
        resp.raise_for_status()
        data = resp.json()

        all_rates = data.get("rates", {})
        rate_date = _clean_date(data.get("time_last_update_utc", ""))
        next_update = _clean_date(data.get("time_next_update_utc", ""))

        state = StateStore()
        prev_all = state.get("exchange_rates", {})
        new_state = {}

        rows = []
        for currency in targets:
            if currency not in all_rates:
                logger.warning("exchange_rates: currency %s not found", currency)
                continue

            rate = float(all_rates[currency])
            pair = f"{base}/{currency}"
            prev = prev_all.get(pair)
            new_state[pair] = rate

            if prev:
                change = rate - float(prev)
                change_pct = (change / float(prev)) * 100 if prev else 0
                if abs(change_pct) < 0.001:
                    trend = "="
                elif change > 0:
                    trend = "UP"
                else:
                    trend = "DOWN"
                prev_out = _smart_round(float(prev))
                change_out = round(change, 4)
                pct_out = round(change_pct, 3)
            else:
                trend = "NEW"
                prev_out = ""
                change_out = ""
                pct_out = ""

            rows.append({
                "pair": pair,
                "base": base,
                "target": currency,
                "rate": _smart_round(rate),
                "previous": prev_out,
                "change": change_out,
                "change_pct": pct_out,
                "trend": trend,
                "inverse": round(1 / rate, 4) if rate else "",
                "per_100": _smart_round(rate * 100),
                "rate_date": rate_date,
                "next_update": next_update,
            })

        state.set("exchange_rates", new_state)
        state.save()

        logger.info("exchange_rates: fetched %d rates (base=%s)", len(rows), base)
        return rows
