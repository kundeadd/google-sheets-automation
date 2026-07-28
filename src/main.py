"""Точка входу: читає config.yaml, тягне дані з увімкнених джерел,
пише в Google Sheets. Запускати вручну або за розкладом (cron/systemd timer).
"""
import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

from sheets_client import SheetsClient
from sources import SOURCE_REGISTRY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

ROOT = Path(__file__).parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    load_dotenv(ROOT / ".env")

    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")

    if not sheet_id:
        logger.error("GOOGLE_SHEET_ID не задано в .env")
        sys.exit(1)
    if not Path(creds_path).exists():
        logger.error("Credentials файл не знайдено: %s", creds_path)
        sys.exit(1)

    config = load_config()
    client = SheetsClient(credentials_path=creds_path, sheet_id=sheet_id)

    for source_conf in config.get("sources", []):
        name = source_conf["name"]
        if not source_conf.get("enabled", True):
            logger.info("Пропускаю вимкнене джерело: %s", name)
            continue

        source_cls = SOURCE_REGISTRY.get(name)
        if not source_cls:
            logger.warning("Невідоме джерело в config.yaml: %s", name)
            continue

        try:
            source = source_cls(source_conf.get("params", {}))
            rows = source.fetch_with_timestamp()
            client.write_rows(
                worksheet_title=source_conf.get("worksheet", name),
                rows=rows,
                mode=source_conf.get("mode", "append"),
            )
        except Exception:
            logger.exception("Помилка при обробці джерела '%s'", name)

    logger.info("Синхронізація завершена")


if __name__ == "__main__":
    main()
