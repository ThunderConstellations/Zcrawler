# Zcrawler

Zcrawler is a modern web application designed for automating data extraction workflows. It specializes in crawling local business information using OpenStreetMap (OSM) data and provides a rich dashboard for managing crawlers, monitoring runs, and visualizing findings.

## Features

- **Custom Crawler Definitions**: Define and save crawler configurations (e.g., location, business types) via the UI.
- **Automated Execution**: Launch crawls with a single click.
- **Real-time Monitoring**: Track the status and progress of crawl runs.
- **Interactive Visualization**: Explore findings on a map, view distance distributions with charts, and browse data in tables.
- **Data Export**: Export your findings to CSV or JSON formats for further analysis.
- **Config-Driven Architecture**: Easily extendable to support different crawler templates and data sources.

## Prerequisites

- **Python 3.10+**
- **pip** (Python package manager)

## Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/Zcrawler.git
   cd Zcrawler
   ```

2. **Install dependencies**:
   ```bash
   pip install -r webapp/requirements.txt
   ```

## Setup

Zcrawler uses SQLite for data storage. The database will be automatically initialized when you first run the application.

1. **Ensure the data directory exists**:
   ```bash
   mkdir -p webapp/app/data
   ```

## Usage

### Running the Webapp

Launch the application from the repository root:

```bash
python run.py
```

The webapp will be available at `http://localhost:8000`.

### Using the App

1. **Create a Definition**: Go to the dashboard and click "+ New Definition". Give it a name and configure the JSON (e.g., set `reference_address` and `city_query`).
2. **Launch a Run**: Use the "Launch Crawler" sidebar to start a crawl. You can select a saved definition or perform an ad-hoc run.
3. **View Findings**: Once a run completes, click "Details" to view the map, charts, and table of results.
4. **Export Data**: Use the "Export CSV" or "Export JSON" buttons on the run details page to download your data.

## Project Structure

- `webapp/app/`: Backend logic (FastAPI, SQLAlchemy models, runner).
- `webapp/templates/`: HTML templates for the dashboard and details pages.
- `scripts/`: Core crawler scripts (OSM integration).
- `output/`: Legacy output folder for business findings.
- `run.py`: Main entry point for the application.

## Core Vision

Refer to [PROJECT_GOALS.md](PROJECT_GOALS.md) for a detailed roadmap and the long-term vision of Zcrawler.
