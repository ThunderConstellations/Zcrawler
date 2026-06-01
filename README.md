# 🕷️ Zcrawler: The AI-Powered Web Intelligence Platform

Zcrawler is a state-of-the-art, modular web crawling and automation platform. Designed for both senior engineers and non-technical users, it bridges the gap between complex web scraping and actionable business intelligence. Whether you're discovering local businesses via OpenStreetMap, scraping dynamic directories with Playwright, or auto-filling job applications, Zcrawler handles the heavy lifting with AI-driven precision.

---

## 🚀 Key Features

- **🧩 Modular Workflow Builder**: Drag-and-drop style sequence builder. Chain Search, Scrape, AI Enrich, Vision Scrape, and Form Automation steps into a single pipeline.
- **🤖 AI-Driven Enrichment**: Integrated with **OpenRouter** (Gemini, Llama, GPT) to automatically summarize websites, extract social links, and find contact emails.
- **👁️ Multimodal Vision Scraping**: Uses AI Vision models to identify and extract data from website screenshots, bypassing complex DOM structures.
- **📄 ATS Form Automation**: Intelligent job application filler that maps your JSON profile to complex forms on Greenhouse, Lever, and more.
- **🛡️ Professional Stealth**: Built-in User-Agent rotation, webdriver masking, and Proxy support to avoid detection and IP bans.
- **📊 Real-time Dashboard**: Interactive Leaflet maps, category distribution charts, and live execution logs.
- **☁️ Cloud Exports**: One-click integration to sync findings with **Airtable** or **Google Sheets**.

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- **Python 3.10+**
- **Node.js** (for Playwright browser engines)
- **OpenRouter API Key** (for AI features)

### 2. Clone and Install
```bash
git clone https://github.com/yourusername/Zcrawler.git
cd Zcrawler
pip install -r webapp/requirements.txt
playwright install chromium
```

### 3. Configuration
You can configure Zcrawler in two ways:
1. **Web UI (Recommended)**: Start the app and go to the **Settings** tab to input your OpenRouter API Key and Proxy URL.
2. **Environment**: Create a `.env` file in the root:
```env
OPENROUTER_API_KEY=sk-or-v1-your-key
PROXY_URL=http://user:pass@host:port
```

---

## 🚦 Running the Project

### Start the Web Application
```bash
# From the root directory
export PYTHONPATH=$PYTHONPATH:.
python3 -m webapp.app.main
```
The dashboard will be available at `http://localhost:8000`.

### CLI Usage (For Developers)
```bash
# Run a specific OSM crawl
python3 scripts/osm_business_crawler.py --reference-address "Valparaiso, IN" --limit 10
```

---

## 📖 Using Every Aspect

### Creating a Modular Workflow
1. Click **New Crawler** on the dashboard.
2. Select **Modular Workflow Builder** as the template.
3. Add steps:
   - **Search Entities**: Uses OpenStreetMap to find businesses near an anchor.
   - **Scrape Details**: Visits found websites using Playwright Stealth.
   - **AI Enrichment**: Converts HTML to Markdown and uses LLMs to extract metadata.
   - **Form Automation**: Navigates to a URL and auto-fills fields using your `default_profile.json`.
   - **Cloud Export**: Automatically pushes findings to Airtable or Google Sheets.

### Using AI Vision
When adding a **Vision Scraper** step, provide a prompt like *"Find the main pricing table and extract the monthly costs"*. Zcrawler will take a high-res screenshot and use Multimodal LLMs to interpret it.

### Semantic Search
In any **Run Detail** page, use the search bar to find findings by "meaning". Typing *"find cozy cafes"* will look through business names and AI-generated summaries to return relevant results.

---

## ⚠️ Error Handling & Troubleshooting

| Error | Likely Cause | Solution |
| :--- | :--- | :--- |
| `API Key Missing` | OpenRouter key not set in Settings. | Go to Settings tab and save your key. |
| `Playwright Timeout` | Site is slow or bot detection is high. | Increase timeout in `crawler_runner.py` or add a Proxy. |
| `JSON Parse Error` | LLM returned conversational text. | Zcrawler has built-in "Sandwich Parsing," but try a more capable model like Gemini 1.5 Pro. |
| `ModuleNotFoundError` | PYTHONPATH not set. | Run with `export PYTHONPATH=$PYTHONPATH:.` |

---

## 🏷️ Tags
`#Python` `#FastAPI` `#AI` `#Playwright` `#WebScraping` `#OpenRouter` `#Automation` `#NoCode` `#DataIntelligence`

---

*Built with ❤️ for the automation community.*
