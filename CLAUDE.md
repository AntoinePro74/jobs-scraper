# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run the scraper:
```bash
python run_scraper.py                    # Run with default search URLs
python run_scraper.py --max-pages 5      # Limit to 5 pages per URL
python run_scraper.py --urls <url>       # Scrape specific URL
```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Architecture

The scraper follows a modular structure:

```
scraper/
├── hellowork_scraper.py    # Main scraper class with Selenium + BeautifulSoup
├── models/
│   └── job_offer.py        # JobOffer dataclass + EmploymentType/RemoteWorkType enums
├── parsers/
│   └── job_details_parser.py  # Extracts details from individual job pages
└── config/
    └── settings.py         # Configuration parameters
```

**Entry points:**
- `main.py` - Basic entry point using `HelloWorkScraper`
- `run_scraper.py` - Full scraper with multiple search URLs, exports to CSV + JSON

**Data flow:**
1. `HelloWorkScraper.scrape_search_with_details()` orchestrates the scraping
2. `scrape_search_results()` - Uses Selenium to handle JavaScript, extracts job titles/URLs from search pages
3. `scrape_job_details()` - Uses `JobDetailsParser` to extract full details (title, company, location, contract type, remote work, salary, description, date) from each job page
4. Results are exported to timestamped CSV and JSON files in `data/`

**Key technologies:**
- Selenium (Chrome) for JavaScript-heavy pages
- BeautifulSoup + lxml for HTML parsing
- pandas for CSV export
- webdriver-manager for ChromeDriver auto-installation
