# sajilo-patro-data

Daily-scraped price data for the **Sajilo Patro** app (gold/silver, fuel, vegetables).

A scheduled GitHub Actions workflow runs the scrapers twice a day and commits
the updated JSON files back to this repo. The app fetches the JSON directly from
`raw.githubusercontent.com`, so this repo doubles as a free, zero-server CDN.

## Layout

```
.
├── .github/workflows/scrape.yml   # runs scrapers on cron
├── scrapers/
│   ├── common.py                  # shared helpers (fetch, write_json, fallback runner)
│   ├── gold_silver.py             # FENEGOSIDA + ShareSansar fallback
│   ├── fuel.py                    # Nepal Oil Corporation
│   ├── vegetables.py              # Kalimati Market
│   └── requirements.txt
└── data/
    ├── gold_silver.json
    ├── fuel.json
    └── vegetables.json
```

## How the app fetches data

The app reads each file directly from GitHub's raw-content CDN:

```
https://raw.githubusercontent.com/<your-username>/sajilo-patro-data/main/data/gold_silver.json
https://raw.githubusercontent.com/<your-username>/sajilo-patro-data/main/data/fuel.json
https://raw.githubusercontent.com/<your-username>/sajilo-patro-data/main/data/vegetables.json
```

These URLs are CDN-cached (~5 minutes). The app additionally caches the response
in AsyncStorage and falls back to the cached copy if the network fails.

## Resilience: why this design survives source outages

1. **Each scraper has a fallback chain.** For example, `gold_silver.py` tries
   FENEGOSIDA first; if it's down (as it often is), it tries ShareSansar.
2. **Failed scrapes do NOT overwrite the previous JSON.** The last-known-good
   data stays in the repo, and the app shows a "last updated X days ago" warning.
3. **Scrapers run independently.** One source failing does not block the others.

## Setup (one-time)

1. **Create a new public repo** on GitHub named `sajilo-patro-data` (must be
   public for the raw-content URL to work without auth, and for free Actions
   minutes to be unlimited).
2. **Copy the contents of this folder** (`data-scraper/`) into the root of that
   repo and push to `main`.
3. Open the repo on GitHub → **Settings → Actions → General**:
   - Workflow permissions: select **"Read and write permissions"** so the bot
     can commit updated JSON back. Save.
4. Open the **Actions** tab → select **"Scrape prices"** → **"Run workflow"**
   to trigger the first run manually. Watch it succeed.
5. Verify the JSON files appeared in `data/` and that
   `https://raw.githubusercontent.com/<you>/sajilo-patro-data/main/data/gold_silver.json`
   returns the JSON in your browser.
6. Tell the app developer your repo URL so the fetch endpoints can be set.

## Running locally

```bash
pip install -r scrapers/requirements.txt
python scrapers/gold_silver.py
python scrapers/fuel.py
python scrapers/vegetables.py
```

Each script writes to `data/<name>.json`. Inspect output, adjust selectors in
the relevant scraper file if a source's HTML has changed.

## When a source's HTML changes

The scrapers are intentionally **loosely-coupled** to source HTML — they search
for tables containing keywords ("gold", "silver", "petrol", etc.) rather than
relying on exact CSS selectors. Still, sites do change. If a scraper starts
failing:

1. Open the source URL in a browser, View Source.
2. Find the new structure of the price section.
3. Adjust the relevant `from_<source>()` function in the scraper file.
4. Test locally with `python scrapers/<name>.py`.
5. Commit and push — next workflow run uses the new code.

## Sources

| File | Primary | Fallback |
| --- | --- | --- |
| `gold_silver.json` | [fenegosida.org](https://www.fenegosida.org) | [sharesansar.com/bullion](https://www.sharesansar.com/bullion) |
| `fuel.json` | [noc.org.np/retailprice](https://noc.org.np/retailprice) | — |
| `vegetables.json` | [kalimatimarket.gov.np/price](https://kalimatimarket.gov.np/price) | — |

All data belongs to the original sources; this repo is a daily snapshot for
non-commercial use within the Sajilo Patro app.
