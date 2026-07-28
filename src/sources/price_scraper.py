"""Парсер ціни товару з публічної сторінки за CSS-селектором.

Типовий кейс для e-commerce: моніторинг ціни конкурента.
Кожен продукт у config.yaml задається як {name, url, selector}.

Приклад:
    products:
      - name: "Product A"
        url: "https://example.com/product-a"
        selector: "span.price"
"""
import logging
import re

import requests
from bs4 import BeautifulSoup

from .base import DataSource

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

PRICE_RE = re.compile(r"[\d]+[\d.,]*")


class PriceScraperSource(DataSource):
    name = "price_scraper"

    def fetch(self) -> list[dict]:
        products = self.config.get("products", [])
        rows = []

        for product in products:
            try:
                price_text = self._scrape_one(product["url"], product["selector"])
            except Exception as exc:
                logger.warning("price_scraper: failed for %s: %s", product.get("name"), exc)
                price_text = None

            rows.append({
                "product": product.get("name"),
                "url": product["url"],
                "price_raw": price_text,
                "price_parsed": self._parse_number(price_text),
            })

        logger.info("price_scraper: fetched %d products", len(rows))
        return rows

    @staticmethod
    def _scrape_one(url: str, selector: str) -> str | None:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        el = soup.select_one(selector)
        return el.get_text(strip=True) if el else None

    @staticmethod
    def _parse_number(text: str | None) -> float | None:
        if not text:
            return None
        match = PRICE_RE.search(text.replace(" ", ""))
        if not match:
            return None
        cleaned = match.group(0).replace(",", ".")
        # якщо два роздільники (тисячі + копійки) — прибрати перший
        if cleaned.count(".") > 1:
            parts = cleaned.split(".")
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        try:
            return float(cleaned)
        except ValueError:
            return None
