"""Entry point: reads config.yaml, pulls data from enabled sources,
writes it to Google Sheets and updates the dashboard.
Run manually or on a schedule (Task Scheduler, cron, systemd timer).
"""
import logging
import os
import sys
from datetime import datetime
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
        logger.error("GOOGLE_SHEET_ID is not set in .env")
        sys.exit(1)
    if not Path(creds_path).exists():
        logger.error("Credentials file not found: %s", creds_path)
        sys.exit(1)

    config = load_config()
    client = SheetsClient(credentials_path=creds_path, sheet_id=sheet_id)

    stats = []
    samples = {}

    for source_conf in config.get("sources", []):
        name = source_conf["name"]
        worksheet = source_conf.get("worksheet", name)
        mode = source_conf.get("mode", "append")

        if not source_conf.get("enabled", True):
            logger.info("Skipping disabled source: %s", name)
            stats.append({
                "source": name, "worksheet": worksheet, "mode": mode,
                "status": "DISABLED", "rows": 0, "finished": "",
            })
            continue

        source_cls = SOURCE_REGISTRY.get(name)
        if not source_cls:
            logger.warning("Unknown source in config.yaml: %s", name)
            stats.append({
                "source": name, "worksheet": worksheet, "mode": mode,
                "status": "ERROR", "rows": 0,
                "finished": datetime.now().strftime("%H:%M:%S"),
            })
            continue

        try:
            source = source_cls(source_conf.get("params", {}))
            rows = source.fetch_with_timestamp()
            samples[name] = rows
            written = client.write_rows(
                worksheet_title=worksheet,
                rows=rows,
                mode=mode,
            )
            stats.append({
                "source": name, "worksheet": worksheet, "mode": mode,
                "status": "OK", "rows": written,
                "finished": datetime.now().strftime("%H:%M:%S"),
            })
        except Exception:
            logger.exception("Failed to process source '%s'", name)
            stats.append({
                "source": name, "worksheet": worksheet, "mode": mode,
                "status": "ERROR", "rows": 0,
                "finished": datetime.now().strftime("%H:%M:%S"),
            })

    if config.get("dashboard", True):
        try:
            client.write_dashboard(stats, samples)
        except Exception:
            logger.exception("Failed to update dashboard")

    ok = sum(1 for s in stats if s["status"] == "OK")
    total = sum(s["rows"] for s in stats)
    logger.info("Sync finished: %d/%d sources ok, %d rows written",
                ok, len(stats), total)


if __name__ == "__main__":
    main()
