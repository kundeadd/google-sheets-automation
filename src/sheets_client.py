"""Google Sheets writer: grouped colored column blocks, banner, borders,
filters, conditional colors and an operations dashboard."""
import logging
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

BANNER_BG = {"red": 0.11, "green": 0.15, "blue": 0.20}
HEADER_BG_DASH = {"red": 0.20, "green": 0.27, "blue": 0.36}
WHITE = {"red": 1.0, "green": 1.0, "blue": 1.0}
DARK_TEXT = {"red": 0.13, "green": 0.16, "blue": 0.20}
GREY_TEXT = {"red": 0.42, "green": 0.42, "blue": 0.42}
BAND_BG = {"red": 0.966, "green": 0.972, "blue": 0.978}
GREEN_FG = {"red": 0.05, "green": 0.50, "blue": 0.20}
RED_FG = {"red": 0.75, "green": 0.12, "blue": 0.12}

OK_BG = {"red": 0.84, "green": 0.93, "blue": 0.85}
ERR_BG = {"red": 0.98, "green": 0.84, "blue": 0.84}
SKIP_BG = {"red": 0.94, "green": 0.94, "blue": 0.94}

GROUP_COLORS = [
    {"red": 0.17, "green": 0.42, "blue": 0.63},
    {"red": 0.16, "green": 0.52, "blue": 0.43},
    {"red": 0.74, "green": 0.46, "blue": 0.13},
    {"red": 0.45, "green": 0.32, "blue": 0.63},
    {"red": 0.69, "green": 0.29, "blue": 0.36},
    {"red": 0.25, "green": 0.47, "blue": 0.56},
]

BORDER_GREY = {"style": "SOLID",
               "color": {"red": 0.78, "green": 0.80, "blue": 0.83}}
BORDER_DARK = {"style": "SOLID_MEDIUM",
               "color": {"red": 0.30, "green": 0.36, "blue": 0.44}}

BODY_FONT = 11
MIN_WIDTH = 105
MAX_WIDTH = 230
PX_PER_CHAR = 9
HEADER_ROWS = 3

RFC_DATE = re.compile(r"^[A-Z][a-z]{2}, \d{1,2} [A-Z][a-z]{2} \d{4}")
ISO_UTC = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}):\d{2}(\s*UTC)?$")

COLUMN_GROUPS = {
    "pair": "Identification", "base": "Identification", "target": "Identification",
    "rate": "Rate and movement", "previous": "Rate and movement",
    "change": "Rate and movement", "change_pct": "Rate and movement",
    "trend": "Rate and movement",
    "inverse": "Conversions", "per_100": "Conversions",
    "city": "Location",
    "temperature_c": "Temperature", "feels_like_c": "Temperature",
    "feels_gap": "Temperature",
    "humidity_pct": "Moisture and sky", "precipitation_mm": "Moisture and sky",
    "cloud_cover_pct": "Moisture and sky",
    "wind_kmh": "Wind", "gusts_kmh": "Wind", "wind_dir": "Wind",
    "pressure_hpa": "Pressure",
    "conditions": "Conditions", "daylight": "Conditions",
    "product": "Product", "name": "Product", "url": "Product",
    "price": "Price", "currency": "Price", "availability": "Price",
    "rate_date": "Timestamps", "next_update": "Timestamps",
    "local_time": "Timestamps", "timezone": "Timestamps",
    "synced_at": "Timestamps", "fetched_at": "Timestamps",
}

NUMERIC_SIGNED = ("change", "change_pct", "feels_gap")


def col_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def tint(c: dict, f: float = 0.80) -> dict:
    return {k: round(c[k] + (1 - c[k]) * f, 3) for k in ("red", "green", "blue")}


def pretty_header(name: str) -> str:
    special = {"pct": "%", "kmh": "km/h", "hpa": "hPa", "mm": "mm",
               "c": "C", "id": "ID", "url": "URL"}
    words = str(name).replace("_", " ").split()
    return " ".join(special.get(w.lower(), w.capitalize()) for w in words)


def clean_value(v):
    if isinstance(v, float):
        return round(v, 4)
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s in ("=", "-", "+"):
        return "FLAT"
    if s.startswith("="):
        return "'" + s
    if RFC_DATE.match(s):
        try:
            return parsedate_to_datetime(s).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return s
    m = ISO_UTC.match(s)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return s


def order_keys(keys):
    by_group = {}
    group_order = []
    for k in keys:
        g = COLUMN_GROUPS.get(k, "Data")
        if g not in by_group:
            by_group[g] = []
            group_order.append(g)
        by_group[g].append(k)
    ordered = []
    for g in group_order:
        ordered.extend(by_group[g])
    return ordered


def build_groups(keys):
    groups = []
    for i, k in enumerate(keys):
        g = COLUMN_GROUPS.get(k, "Data")
        if groups and groups[-1][0] == g:
            groups[-1][2] = i + 1
        else:
            groups.append([g, i, i + 1])
    return groups


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


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
            return self._spreadsheet.add_worksheet(title=title, rows=2000, cols=cols)

    def _batch(self, requests, label=""):
        if not requests:
            return
        try:
            self._spreadsheet.batch_update({"requests": requests})
        except Exception as e:
            logger.error("format step '%s' failed: %s", label, e)

    def _widths(self, ws, table):
        if not table:
            return []
        ncols = len(table[0])
        out = []
        for i in range(ncols):
            longest = max(len(str(r[i])) for r in table if i < len(r))
            width = max(MIN_WIDTH, min(MAX_WIDTH, longest * PX_PER_CHAR + 26))
            out.append({
                "updateDimensionProperties": {
                    "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                              "startIndex": i, "endIndex": i + 1},
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            })
        return out

    def _row_height(self, sid, idx, px):
        return {"updateDimensionProperties": {
            "range": {"sheetId": sid, "dimension": "ROWS",
                      "startIndex": idx, "endIndex": idx + 1},
            "properties": {"pixelSize": px}, "fields": "pixelSize"}}

    def _cell_style(self, sid, r1, r2, c1, c2, fmt, fields):
        return {"repeatCell": {
            "range": {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                      "startColumnIndex": c1, "endColumnIndex": c2},
            "cell": {"userEnteredFormat": fmt},
            "fields": "userEnteredFormat(" + fields + ")"}}

    def _merge(self, sid, r1, r2, c1, c2):
        return {"mergeCells": {"range": {
            "sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
            "startColumnIndex": c1, "endColumnIndex": c2},
            "mergeType": "MERGE_ALL"}}

    def _tbl_border(self, sid, r1, r2, c1, c2):
        return {"updateBorders": {
            "range": {"sheetId": sid, "startRowIndex": r1, "endRowIndex": r2,
                      "startColumnIndex": c1, "endColumnIndex": c2},
            "top": BORDER_DARK, "bottom": BORDER_DARK,
            "left": BORDER_DARK, "right": BORDER_DARK,
            "innerHorizontal": BORDER_GREY, "innerVertical": BORDER_GREY}}

    def _clear_decorations(self, ws):
        try:
            meta = self._spreadsheet.fetch_sheet_metadata()
        except Exception:
            return
        req = []
        for sh in meta.get("sheets", []):
            if sh.get("properties", {}).get("sheetId") != ws.id:
                continue
            for b in sh.get("bandedRanges", []):
                req.append({"deleteBanding": {"bandedRangeId": b["bandedRangeId"]}})
            n = len(sh.get("conditionalFormats", []))
            for i in range(n - 1, -1, -1):
                req.append({"deleteConditionalFormatRule":
                            {"sheetId": ws.id, "index": i}})
        self._batch(req, "clear old decorations")

    # ---------- data worksheets ----------

    def _structure(self, ws, groups, ncols, last_row):
        sid = ws.id
        req = [
            {"unmergeCells": {"range": {
                "sheetId": sid, "startRowIndex": 0, "endRowIndex": HEADER_ROWS,
                "startColumnIndex": 0, "endColumnIndex": ws.col_count}}},
            self._merge(sid, 0, 1, 0, ncols),
            self._cell_style(sid, 0, 1, 0, ncols, {
                "backgroundColor": BANNER_BG, "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 13,
                               "foregroundColor": WHITE}},
                "backgroundColor,verticalAlignment,textFormat"),
            self._row_height(sid, 0, 40),
            self._row_height(sid, 1, 26),
            self._row_height(sid, 2, 30),
            {"updateSheetProperties": {
                "properties": {"sheetId": sid,
                               "gridProperties": {"frozenRowCount": HEADER_ROWS}},
                "fields": "gridProperties.frozenRowCount"}},
        ]

        for gi, (gname, start, end) in enumerate(groups):
            color = GROUP_COLORS[gi % len(GROUP_COLORS)]
            light = tint(color)
            if end - start > 1:
                req.append(self._merge(sid, 1, 2, start, end))
            req.append(self._cell_style(sid, 1, 2, start, end, {
                "backgroundColor": color, "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": WHITE}},
                "backgroundColor,horizontalAlignment,verticalAlignment,textFormat"))
            req.append(self._cell_style(sid, 2, 3, start, end, {
                "backgroundColor": light, "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": DARK_TEXT}},
                "backgroundColor,verticalAlignment,wrapStrategy,textFormat"))

        if last_row > HEADER_ROWS:
            req.append(self._cell_style(sid, HEADER_ROWS, last_row, 0, ncols, {
                "verticalAlignment": "MIDDLE",
                "textFormat": {"fontSize": BODY_FONT}},
                "verticalAlignment,textFormat"))
        return req

    def _banding(self, sid, ncols, last_row):
        if last_row <= HEADER_ROWS:
            return []
        return [{"addBanding": {"bandedRange": {
            "range": {"sheetId": sid, "startRowIndex": HEADER_ROWS,
                      "endRowIndex": last_row, "startColumnIndex": 0,
                      "endColumnIndex": ncols},
            "rowProperties": {"firstBandColor": WHITE,
                              "secondBandColor": BAND_BG}}}}]

    def _filter(self, sid, ncols, last_row):
        return [{"setBasicFilter": {"filter": {
            "range": {"sheetId": sid, "startRowIndex": 2, "endRowIndex": last_row,
                      "startColumnIndex": 0, "endColumnIndex": ncols}}}}]

    def _conditional(self, sid, keys, last_row):
        req = []
        for i, k in enumerate(keys):
            if k in NUMERIC_SIGNED:
                rng = {"sheetId": sid, "startRowIndex": HEADER_ROWS,
                       "endRowIndex": last_row, "startColumnIndex": i,
                       "endColumnIndex": i + 1}
                for cond, fg in (("NUMBER_GREATER", GREEN_FG),
                                 ("NUMBER_LESS", RED_FG)):
                    req.append({"addConditionalFormatRule": {"rule": {
                        "ranges": [rng],
                        "booleanRule": {
                            "condition": {"type": cond,
                                          "values": [{"userEnteredValue": "0"}]},
                            "format": {"textFormat": {
                                "bold": True, "foregroundColor": fg}}}},
                        "index": 0}})
        if "trend" in keys:
            i = keys.index("trend")
            rng = {"sheetId": sid, "startRowIndex": HEADER_ROWS,
                   "endRowIndex": last_row, "startColumnIndex": i,
                   "endColumnIndex": i + 1}
            for word, fg in (("UP", GREEN_FG), ("DOWN", RED_FG),
                             ("FLAT", GREY_TEXT)):
                req.append({"addConditionalFormatRule": {"rule": {
                    "ranges": [rng],
                    "booleanRule": {
                        "condition": {"type": "TEXT_EQ",
                                      "values": [{"userEnteredValue": word}]},
                        "format": {"textFormat": {
                            "bold": True, "foregroundColor": fg}}}},
                    "index": 0}})
        return req

    def write_rows(self, worksheet_title: str, rows: list[dict],
                   mode: str = "append") -> int:
        if not rows:
            logger.info("write_rows: no rows for '%s', skipping", worksheet_title)
            return 0

        keys = order_keys(list(rows[0].keys()))
        ncols = len(keys)
        headers = [pretty_header(k) for k in keys]
        groups = build_groups(keys)

        group_row = [""] * ncols
        for gname, start, _ in groups:
            group_row[start] = gname

        ws = self._get_or_create_worksheet(worksheet_title, cols=max(ncols, 12))
        values = [[clean_value(r.get(k, "")) for k in keys] for r in rows]

        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        existing = [] if mode == "replace" else ws.get_all_values()
        fresh = mode == "replace" or len(existing) < HEADER_ROWS

        if fresh:
            ws.clear()
            banner = [f"{worksheet_title.upper()}   |   updated {stamp}   |   "
                      f"{len(values)} rows"] + [""] * (ncols - 1)
            ws.update(values=[banner, group_row, headers] + values,
                      range_name="A1", value_input_option="USER_ENTERED")
            last_row = HEADER_ROWS + len(values)
        else:
            ws.append_rows(values, value_input_option="USER_ENTERED")
            total = len(existing) - HEADER_ROWS + len(values)
            ws.update(values=[[f"{worksheet_title.upper()}   |   updated {stamp}"
                               f"   |   {total} rows"]],
                      range_name="A1", value_input_option="USER_ENTERED")
            last_row = len(existing) + len(values)

        sid = ws.id
        self._clear_decorations(ws)
        self._batch(self._structure(ws, groups, ncols, last_row), "structure")
        self._batch([self._tbl_border(sid, 1, last_row, 0, ncols)], "borders")
        self._batch(self._banding(sid, ncols, last_row), "banding")
        self._batch(self._filter(sid, ncols, last_row), "filter")
        self._batch(self._conditional(sid, keys, last_row), "conditional")
        self._batch(self._widths(ws, [headers] + values[:80]), "widths")

        logger.info("write_rows: wrote %d rows to '%s' (mode=%s)",
                    len(rows), worksheet_title, mode)
        return len(rows)

    # ---------- dashboard ----------

    def write_dashboard(self, stats: list[dict], samples: dict | None = None,
                        title: str = "Dashboard"):
        samples = samples or {}
        rates = weather = None
        for rows in samples.values():
            if rows and isinstance(rows[0], dict):
                if "pair" in rows[0]:
                    rates = rows
                elif "city" in rows[0]:
                    weather = rows

        NC = 6
        ws = self._get_or_create_worksheet(title, cols=max(NC, 8))
        ws.clear()
        self._clear_decorations(ws)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_rows = sum(s.get("rows", 0) for s in stats)
        ok = sum(1 for s in stats if s.get("status") == "OK")
        failed = sum(1 for s in stats if s.get("status") == "ERROR")

        body = []

        def row(vals):
            body.append(list(vals) + [""] * (NC - len(vals)))
            return len(body) - 1

        i_banner = row(["DATA SYNC DASHBOARD"])
        i_sub = row([f"Last run {now}   |   automated pipeline: "
                     f"APIs -> Python -> Google Sheets"])
        row([])
        i_kpi_h = row(["Sources", "Success", "Failed", "Rows Written",
                       "Currencies", "Cities"])
        i_kpi_v = row([len(stats), ok, failed, total_rows,
                       len(rates or []), len(weather or [])])
        row([])

        i_sync_band = row(["SYNC LOG"])
        i_sync_h = row(["Source", "Worksheet", "Mode", "Status", "Rows",
                        "Finished"])
        sync_rows = []
        for s in stats:
            sync_rows.append(row([s.get("source", ""), s.get("worksheet", ""),
                                  s.get("mode", ""), s.get("status", ""),
                                  s.get("rows", 0), s.get("finished", "")]))

        i_mkt_band = i_mkt_h = None
        mkt_rows = []
        if rates:
            row([])
            i_mkt_band = row(["TOP CURRENCY MOVES  (USD base)"])
            i_mkt_h = row(["Pair", "Rate", "Previous", "Change %", "Trend",
                           "Rate Date"])
            top = sorted(rates, key=lambda r: abs(_f(r.get("change_pct"))),
                         reverse=True)[:10]
            for r in top:
                mkt_rows.append((row([
                    r.get("pair", ""), r.get("rate", ""), r.get("previous", ""),
                    r.get("change_pct", ""), clean_value(str(r.get("trend", ""))),
                    clean_value(str(r.get("rate_date", "")))]),
                    str(r.get("trend", ""))))

        i_wx_band = i_wx_h = None
        wx_rows = []
        if weather:
            row([])
            i_wx_band = row(["WEATHER OVERVIEW  (warmest first)"])
            i_wx_h = row(["City", "Temp C", "Feels Like", "Wind km/h",
                          "Conditions", "Daylight"])
            top = sorted(weather, key=lambda r: _f(r.get("temperature_c"), -999),
                         reverse=True)[:10]
            for r in top:
                wx_rows.append(row([
                    r.get("city", ""), r.get("temperature_c", ""),
                    r.get("feels_like_c", ""), r.get("wind_kmh", ""),
                    r.get("conditions", ""), r.get("daylight", "")]))

        row([])
        i_footer = row(["Generated automatically  |  Python + gspread + "
                        "Google Sheets API"])

        ws.update(values=body, range_name="A1",
                  value_input_option="USER_ENTERED")

        sid = ws.id
        n_rows = len(body)
        req = [
            {"unmergeCells": {"range": {
                "sheetId": sid, "startRowIndex": 0, "endRowIndex": n_rows + 5,
                "startColumnIndex": 0, "endColumnIndex": ws.col_count}}},
            self._merge(sid, i_banner, i_banner + 1, 0, NC),
            self._cell_style(sid, i_banner, i_banner + 1, 0, NC, {
                "backgroundColor": BANNER_BG, "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 16,
                               "foregroundColor": WHITE}},
                "backgroundColor,verticalAlignment,textFormat"),
            self._row_height(sid, i_banner, 44),
            self._merge(sid, i_sub, i_sub + 1, 0, NC),
            self._cell_style(sid, i_sub, i_sub + 1, 0, NC, {
                "textFormat": {"fontSize": 10, "italic": True,
                               "foregroundColor": GREY_TEXT}},
                "textFormat"),
            {"updateSheetProperties": {
                "properties": {"sheetId": sid,
                               "gridProperties": {"frozenRowCount": 2}},
                "fields": "gridProperties.frozenRowCount"}},
            self._row_height(sid, i_kpi_v, 36),
        ]

        for j in range(NC):
            req.append(self._cell_style(sid, i_kpi_h, i_kpi_h + 1, j, j + 1, {
                "backgroundColor": GROUP_COLORS[j % len(GROUP_COLORS)],
                "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": WHITE}},
                "backgroundColor,horizontalAlignment,verticalAlignment,textFormat"))
        req.append(self._cell_style(sid, i_kpi_v, i_kpi_v + 1, 0, NC, {
            "horizontalAlignment": "CENTER", "verticalAlignment": "MIDDLE",
            "textFormat": {"bold": True, "fontSize": 18}},
            "horizontalAlignment,verticalAlignment,textFormat"))
        req.append(self._tbl_border(sid, i_kpi_h, i_kpi_v + 1, 0, NC))

        def section(band_i, header_i, data_first, data_last, band_color):
            req.append(self._merge(sid, band_i, band_i + 1, 0, NC))
            req.append(self._cell_style(sid, band_i, band_i + 1, 0, NC, {
                "backgroundColor": band_color, "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 11,
                               "foregroundColor": WHITE}},
                "backgroundColor,verticalAlignment,textFormat"))
            req.append(self._row_height(sid, band_i, 28))
            req.append(self._cell_style(sid, header_i, header_i + 1, 0, NC, {
                "backgroundColor": HEADER_BG_DASH, "verticalAlignment": "MIDDLE",
                "textFormat": {"bold": True, "fontSize": 10,
                               "foregroundColor": WHITE}},
                "backgroundColor,verticalAlignment,textFormat"))
            if data_last >= data_first:
                req.append(self._cell_style(sid, data_first, data_last + 1,
                                            0, NC, {
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"fontSize": BODY_FONT}},
                    "verticalAlignment,textFormat"))
            req.append(self._tbl_border(sid, band_i, data_last + 1, 0, NC))

        section(i_sync_band, i_sync_h, sync_rows[0] if sync_rows else i_sync_h,
                sync_rows[-1] if sync_rows else i_sync_h, GROUP_COLORS[0])
        for i, s in zip(sync_rows, stats):
            status = s.get("status")
            bg = OK_BG if status == "OK" else ERR_BG if status == "ERROR" \
                else SKIP_BG
            req.append(self._cell_style(sid, i, i + 1, 0, NC,
                                        {"backgroundColor": bg},
                                        "backgroundColor"))

        if rates and mkt_rows:
            section(i_mkt_band, i_mkt_h, mkt_rows[0][0], mkt_rows[-1][0],
                    GROUP_COLORS[1])
            for i, trend in mkt_rows:
                fg = GREEN_FG if trend == "UP" else RED_FG if trend == "DOWN" \
                    else GREY_TEXT
                req.append(self._cell_style(sid, i, i + 1, 3, 5, {
                    "textFormat": {"bold": True, "fontSize": BODY_FONT,
                                   "foregroundColor": fg}},
                    "textFormat"))

        if weather and wx_rows:
            section(i_wx_band, i_wx_h, wx_rows[0], wx_rows[-1],
                    GROUP_COLORS[3])

        req.append(self._merge(sid, i_footer, i_footer + 1, 0, NC))
        req.append(self._cell_style(sid, i_footer, i_footer + 1, 0, NC, {
            "textFormat": {"fontSize": 9, "italic": True,
                           "foregroundColor": GREY_TEXT}},
            "textFormat"))

        self._batch(req, "dashboard")

        widths = []
        for j in range(NC):
            widths.append({"updateDimensionProperties": {
                "range": {"sheetId": sid, "dimension": "COLUMNS",
                          "startIndex": j, "endIndex": j + 1},
                "properties": {"pixelSize": 165}, "fields": "pixelSize"}})
        self._batch(widths, "dashboard widths")
        logger.info("dashboard updated: %d sources, %d rows", len(stats),
                    total_rows)
