# data-use

Personal data hosting — daily-refreshed JSON snapshots and static configuration files, served via GitHub's raw CDN and jsDelivr.

## Layout

```
.
├── .github/workflows/scrape.yml   # runs scrapers on a cron schedule
├── scrapers/                      # Python scraping jobs
│   ├── common.py
│   ├── gold_silver.py
│   ├── fuel.py
│   ├── vegetables.py
│   └── requirements.txt
└── data/                          # JSON output
    ├── gold_silver.json
    ├── gold_silver_history.json
    ├── fuel.json
    ├── vegetables.json
    └── forex.json
```

## Design notes

- Each scraper has a fallback chain. A primary source failure tries the next.
- Failed scrapes do NOT overwrite the previous JSON — last-known-good data stays in place.
- Scrapers run independently. One source failing does not block the others.

## Running scrapers locally

```bash
pip install -r scrapers/requirements.txt
python scrapers/gold_silver.py
python scrapers/fuel.py
python scrapers/vegetables.py
```

Each script writes to `data/<name>.json`. Adjust selectors in the relevant scraper file if a source's HTML has changed.

## License

Personal use. All scraped data belongs to the original publishers.
