# google-sheets-automation

Pulls data from APIs and web pages, writes it into Google Sheets on a schedule. No manual copy-pasting into spreadsheets.

## What it does

Three data sources, each one a separate Python module. Turn them on/off in config.yaml, no code touching needed.

- Exchange rates (USD, EUR, UAH, GBP, PLN, CHF, JPY) from open.er-api.com
- Weather for a list of cities from Open-Meteo
- Price scraper, grabs a price off any page using a CSS selector, good for watching a competitor's pricing

Each source writes to its own worksheet inside one spreadsheet.

## Stack

Python, gspread, requests, BeautifulSoup. Google Sheets API + Drive API with a service account, no OAuth login flow needed.

## Run

```bash
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
sources:
  - name: exchange_rates
    enabled: true
    worksheet: "Курси валют"
    mode: append
    params:
      base_currency: USD
      target_currencies: [EUR, UAH, GBP, PLN, CHF, JPY]

  - name: weather
    enabled: true
    worksheet: "Погода"
    mode: append
    params:
      cities:
        - name: "Kyiv"
          lat: 50.4501
          lon: 30.5234

  - name: price_scraper
    enabled: false
    worksheet: "Ціни конкурентів"
    mode: replace
    params:
      products:
        - name: "Example Product"
          url: "https://example.com/product"
          selector: "span.price"
```

`mode: append` keeps a history, new rows get added every run. `mode: replace` wipes the sheet and writes fresh data, good for a live snapshot like current prices.

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

```powershell
schtasks /create /tn "SheetsAutomation" /tr "'<path>\venv\Scripts\python.exe' '<path>\src\main.py'" /sc hourly /st 09:00 /f
```

Linux cron, daily at 9am:

```bash
0 9 * * * cd /opt/google-sheets-automation && venv/bin/python3 src/main.py >> sync.log 2>&1
```