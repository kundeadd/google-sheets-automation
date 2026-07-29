# google-sheets-automation

Pulls data from APIs and web pages, writes it into Google Sheets on a schedule. No manual copy-pasting into spreadsheets.

## What it does

Three data sources, each one a separate Python module. Turn them on/off in config.yaml, no code touching needed.

* Exchange rates for 30 currencies from open.er-api.com, with change against the previous run
* Weather for 25 cities from Open-Meteo, 15 data points per city
* Price scraper, grabs a price off any page using a CSS selector, good for watching a competitor's pricing

Each source writes to its own worksheet inside one spreadsheet. A Dashboard worksheet is generated on every run.

## Sheet formatting

The script does not dump raw rows. Every worksheet gets:

* a title banner with the run time and row count
* colored column groups above the header row, so wide tables stay readable
* a filter row and frozen header
* alternating row colors and borders
* green and red text on change columns and trend values

The Dashboard worksheet shows KPI cards (sources, success, failed, rows written, currencies, cities), a sync log with per source status, the top currency moves, and a weather overview.

## Stack

Python, gspread, requests, BeautifulSoup. Google Sheets API + Drive API with a service account, no OAuth login flow needed.

## Run

```
pip install -r requirements.txt
cp .env.example .env
python src/main.py
```

Fill in `.env` first: your Sheet ID and path to the service account JSON key.

## Getting the Google API access

1. Google Cloud Console, new project, enable Sheets API and Drive API
2. IAM > Service Accounts > create one > Keys > Create new key > JSON, save it as credentials.json
3. Open your Sheet, Share, paste the service account's email, give it Editor
4. Sheet ID is in the URL, between /d/ and /edit

## config.yaml

```yaml
dashboard: true

sources:
  - name: exchange_rates
    enabled: true
    worksheet: "Exchange Rates"
    mode: append
    params:
      base_currency: USD
      target_currencies: [EUR, UAH, GBP, PLN, CHF, JPY, CAD, AUD, CNY, SEK]

  - name: weather
    enabled: true
    worksheet: "Weather"
    mode: append
    params:
      cities:
        - {name: "Kyiv", lat: 50.4501, lon: 30.5234}
        - {name: "Warsaw", lat: 52.2297, lon: 21.0122}

  - name: price_scraper
    enabled: false
    worksheet: "Competitor Prices"
    mode: replace
    params:
      products:
        - name: "Example Product"
          url: "https://example.com/product"
          selector: "span.price"
```

`mode: append` keeps a history, new rows get added every run. `mode: replace` wipes the sheet and writes fresh data, good for a live snapshot like current prices.

Set `dashboard: false` to skip the Dashboard worksheet.

## Column groups

Columns are grouped by name in `COLUMN_GROUPS` inside `src/sheets_client.py`. Columns of the same group are moved next to each other and get a colored band above the header. Unknown columns fall into a group called Data, so a new source works without any config.

## Tracking change between runs

`src/state_store.py` writes the last values into `.state.json` next to the project. The exchange rates source reads it and fills the Previous, Change, Change % and Trend columns. First run shows NEW, every run after that shows the real movement.

## Adding your own source

```python
# src/sources/my_source.py
from .base import DataSource

class MySource(DataSource):
    name = "my_source"

    def fetch(self) -> list[dict]:
        return [{"col_a": "value", "col_b": 123}]
```

Add it to `SOURCE_REGISTRY` in `src/sources/__init__.py` and list it in config.yaml.

## Scheduling

Windows, hourly:

```
schtasks /create /tn "SheetsAutomation" /tr "'<path>\venv\Scripts\python.exe' '<path>\src\main.py'" /sc hourly /st 09:00 /f
```

Linux cron, daily at 9am:

```
0 9 * * * cd /opt/google-sheets-automation && venv/bin/python3 src/main.py >> sync.log 2>&1
```

## Notes

Open-Meteo drops connections when you hit it with a long city list. The weather source retries three times per city and pauses between requests, so a single failure does not kill the run.
