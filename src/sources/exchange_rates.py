"""Курси валют через open.er-api.com (безкоштовний, без ключа, включає UAH)."""
import logging

import requests

from .base import DataSource

logger = logging.getLogger(__name__)

API_URL = "https://open.er-api.com/v6/latest/{base}"


class ExchangeRatesSource(DataSource):
    name = "exchange_rates"

    def fetch(self) -> list[dict]:
        base = self.config.get("base_currency", "USD")
        targets = self.config.get("target_currencies", ["EUR", "UAH", "GBP"])

        resp = requests.get(API_URL.format(base=base), timeout=10)
        resp.raise_for_status()
        data = resp.json()
        all_rates = data.get("rates", {})

        rows = []
        for currency in targets:
            if currency not in all_rates:
                logger.warning("exchange_rates: currency %s not found", currency)
                continue
            rows.append({
                "base_currency": base,
                "target_currency": currency,
                "rate": all_rates[currency],
                "date": data.get("time_last_update_utc", ""),
            })

        logger.info("exchange_rates: fetched %d rates (base=%s)", len(rows), base)
        return rows