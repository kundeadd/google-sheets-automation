"""Тонка обгортка над gspread для запису рядків у Google Sheets."""
import logging

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class SheetsClient:
    def __init__(self, credentials_path: str, sheet_id: str):
        creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
        self._client = gspread.authorize(creds)
        self._spreadsheet = self._client.open_by_key(sheet_id)

    def _get_or_create_worksheet(self, title: str, cols: int = 20):
        try:
            return self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            logger.info("Creating worksheet '%s'", title)
            return self._spreadsheet.add_worksheet(title=title, rows=1000, cols=cols)

    def write_rows(self, worksheet_title: str, rows: list[dict], mode: str = "append"):
        """Записує рядки у вказаний лист.

        mode="append" — додає в кінець (append-only лог, напр. історія курсів).
        mode="replace" — очищає лист і записує заново (снепшот, напр. поточні ціни).
        """
        if not rows:
            logger.info("write_rows: no rows for '%s', skipping", worksheet_title)
            return

        ws = self._get_or_create_worksheet(worksheet_title, cols=max(len(rows[0]), 10))
        headers = list(rows[0].keys())
        values = [list(row.get(h, "") for h in headers) for row in rows]

        if mode == "replace":
            ws.clear()
            ws.update([headers] + values)
        else:  # append
            existing = ws.get_all_values()
            if not existing:
                ws.append_row(headers)
            ws.append_rows(values)

        logger.info("write_rows: wrote %d rows to '%s' (mode=%s)", len(rows), worksheet_title, mode)
