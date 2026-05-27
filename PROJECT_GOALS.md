# Project Goals: Zcrawler Webapp

## Core Vision
The objective is to evolve Zcrawler from a set of scripts into a comprehensive web application. This platform will allow users to:
- **Manage Crawlers**: View lists of previously created crawlers and their configurations.
- **Explore Findings**: Browse findings (e.g., business lists) from previous crawls in a graphically pleasing and interactive manner (tables, maps, charts).
- **Create Custom Crawlers**: Easily define new crawlers through a user-friendly UI without writing code.
- **Automated Execution**: Automate the creation and execution of crawlers directly within the webapp.
- **Real-time Monitoring**: View logs and progress of active crawls.

## Current State
- **Valparaiso Crawler**: A functional OpenStreetMap (OSM) based crawler for businesses in Valparaiso, IN.
- **Webapp MVP**: A FastAPI-based backend with a basic SQLite database for tracking runs and findings.
- **Basic UI**: Simple HTML templates using Tailwind CSS, Leaflet for maps, and Chart.js for data visualization.

## Research Findings
Based on existing open-source projects:
- **Crawlab**: Reference for distributed crawler orchestration and multi-run management.
- **Gerapy/ScrapydWeb**: Reference for Python-first crawler dashboards and operational UX.
- **Open Agent Builder/n8n**: Reference for visual "builder canvas" and node-based workflows.
- **Crawlee/Crawl4AI**: Reference for resilient and extraction-focused crawler runtimes.

## Planned Improvements & Features
- [ ] **Generic Crawler Framework**: Move away from hardcoded scripts to a configuration-driven model.
- [ ] **Crawler Definition UI**: Build a form/canvas for users to define their own crawler parameters (e.g., city, business types, extraction rules).
- [ ] **Advanced Visualization**: Enhanced maps with heatmaps, better data filtering, and export capabilities (CSV, JSON, PDF).
- [ ] **Job Scheduling**: Support for periodic or scheduled crawls.
- [ ] **Authentication & Multi-tenancy**: Allow different users to manage their own crawlers and findings.

## Development Principles
- **Resourceful & Autonomous**: Use tools and research to solve problems without constant guidance.
- **Verify Always**: Every change must be verified through testing or inspection.
- **No Vibe Coding**: Ensure code is robust, documented, and follows engineering best practices.

## Recent Progress
- **Repository Cleanup**: Removed redundant helper scripts (`userinput.py`) and old temporary files to streamline the codebase.
- **Backend Generalization**: Refactored the database schema to include `CrawlerDefinition`, allowing users to save and reuse crawler configurations.
- **Config-Driven Runner**: Refactored `crawler_runner.py` to use JSON configurations from definitions, enabling dynamic parameters for OSM-based crawls.
- **Modern Dashboard**: Rebuilt the web UI with a dark theme, adding sections for managing crawler definitions, launching runs (ad-hoc or via definition), and viewing a summary of project statistics.
- **Functional Verification**: Confirmed that the end-to-end flow (Definition -> Run -> Findings) works correctly via the FastAPI backend.

- **Modern Run Details Page**: Overhauled `run_detail.html` with a consistent dark theme, dynamic status badges, and enhanced visualizations (400px height for maps/charts).
- **Data Export Capability**: Added client-side CSV and JSON export features to the run details page, allowing users to easily download their findings.

- **Documentation & Entry Point**: Created a `run.py` entry point at the root to resolve module path issues and updated `README.md` with comprehensive setup and usage guides.
