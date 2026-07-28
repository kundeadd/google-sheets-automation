"""Базовий інтерфейс для джерела даних.

Кожне джерело (курси валют, погода, парсер цін тощо) наслідує цей клас
і реалізує fetch(), який повертає список рядків для запису в Google Sheets.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class DataSource(ABC):
    """Абстрактне джерело даних для синхронізації з Google Sheets."""

    name: str = "unnamed_source"

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Повертає список рядків. Кожен dict — один рядок таблиці.

        Ключі dict стають заголовками колонок (у порядку першого рядка).
        """
        raise NotImplementedError

    def fetch_with_timestamp(self) -> list[dict]:
        """Обгортка: додає timestamp до кожного рядка перед записом."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        rows = self.fetch()
        for row in rows:
            row.setdefault("synced_at", ts)
        return rows
