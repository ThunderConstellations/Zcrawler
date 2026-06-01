# Zcrawler 🕷️

Zcrawler is a high-performance web platform for automated local business discovery and data enrichment. It leverages OpenStreetMap (OSM) data and AI-powered web scraping to build comprehensive lead databases with geographic precision.

## 🚀 Key Features

- **Geographic Precision**: Anchor your searches with a reference address and define a specific search radius.
- **Rich Data Enrichment**: Automatically scrapes business websites to extract OpenGraph descriptions, social links, and contact emails.
- **Visual Intelligence**: Interactive Leaflet-based maps, mark clustering, and category distribution charts (Chart.js).
- **Automated Scheduling**: Set up recurring crawls to monitor changes in your target areas.
- **Pro Dashboard**: Modern dark-themed UI built with Tailwind CSS for managing definitions, schedules, and run history.
- **Extensible Architecture**: Support for multiple crawler templates (OSM, Generic Directory Scrapers).

## 🛠️ Technical Stack

- **Backend**: FastAPI (Python 3.10+)
- **Database**: SQLite with SQLAlchemy ORM
- **Crawler**: Custom OSM/Overpass integration
- **Frontend**: Tailwind CSS, Leaflet.js, Chart.js, FontAwesome
- **Asynchronous**: Built-in task scheduler and background execution

## ⚙️ Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/Zcrawler.git
   cd Zcrawler
   ```

2. **Install dependencies**:
   ```bash
   pip install -r webapp/requirements.txt
   ```

## 🚦 Quick Start

### 1. Initialize the App
Zcrawler handles database initialization and directory setup automatically on first run.

### 2. Run the Web Server
Launch the platform using the provided entry point:
```bash
python run.py
```
The dashboard will be available at `http://localhost:8000`.

### 3. Basic Workflow
1. **Create a Definition**: Go to the **Definitions** tab and create a new OSM Crawler configuration. Set your target city (e.g., "Valparaiso, IN") and optional categories (e.g., "restaurant, cafe").
2. **Launch a Run**: From the Dashboard sidebar, select your definition and click **Launch Crawler**.
3. **Analyze Results**: Once completed (indicated by the pulsing status badge), click **View Results** to explore findings on the map and table.

## 📁 Project Structure

```text
.
├── scripts/                # Core crawler scripts
│   ├── osm_business_crawler.py  # OSM/Overpass extractor
│   └── directory_scraper.py     # Generic scraper template
├── webapp/
│   ├── app/                # FastAPI backend logic
│   │   ├── crawler_runner.py # Execution & persistence layer
│   │   ├── enrichment.py     # Web scraping & AI logic
│   │   ├── scheduler.py      # Background task manager
│   │   └── models.py         # SQLAlchemy schemas
│   ├── templates/          # Modern UI templates
│   └── storage/            # Data persistence (SQLite & Run artifacts)
└── run.py                  # Main entry point
```

## 🛡️ Reliability Features

- **Endpoint Retries**: The OSM crawler automatically retries across multiple Overpass mirrors if one fails.
- **Rate Limiting Compliance**: Built-in delays for Nominatim geocoding to respect OSM usage policies.
- **Error Transparency**: Real-time log terminal in the UI for debugging failed runs.

---
*Built with passion for data engineers and lead generation specialists.*
