import re
import json
import os
import time
import httpx
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import html2text
from dotenv import load_dotenv
from webapp.app.db import SessionLocal
from webapp.app.models import SystemSetting

load_dotenv()

def get_api_key():
    """Get API key from DB or environment."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        try:
            with SessionLocal() as db:
                setting = db.get(SystemSetting, "OPENROUTER_API_KEY")
                if setting:
                    key = setting.value
        except Exception:
            pass
    return key

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def call_openrouter(prompt: str, model: str = "google/gemini-2.0-flash-001", retries: int = 3) -> Optional[str]:
    """Call OpenRouter API with a prompt and basic retry logic."""
    api_key = get_api_key()
    if not api_key:
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yourusername/Zcrawler",
        "X-Title": "Zcrawler"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    for attempt in range(retries):
        try:
            with httpx.Client() as client:
                response = client.post(OPENROUTER_URL, headers=headers, json=payload, timeout=45.0)
                if response.status_code == 429: # Rate limit
                     wait = (attempt + 1) * 5
                     print(f"Rate limited. Waiting {wait}s...")
                     time.sleep(wait)
                     continue
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenRouter API error (attempt {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None

def extract_basic_info_from_url(url: str) -> Dict[str, str]:
    """Scrape website meta tags for description and look for social links."""
    if not url or url == "N/A":
        return {}

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        with httpx.Client(headers=headers, follow_redirects=True) as client:
            response = client.get(url, timeout=10.0)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # Find description
            description = ""
            desc_tag = soup.find('meta', attrs={'name': 'description'}) or \
                       soup.find('meta', attrs={'property': 'og:description'})
            if desc_tag:
                description = desc_tag.get('content', '')

            # Find title
            title = soup.title.string.strip() if soup.title else ""

            # Look for common social links
            socials = {}
            for platform in ['facebook', 'instagram', 'twitter', 'linkedin']:
                link = soup.find('a', href=re.compile(rf'{platform}\.com', re.I))
                if link:
                    socials[platform] = link['href']

            # Try to find an email
            email = ""
            email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html)
            if email_match:
                email = email_match.group(0)

            return {
                "description": description,
                "title": title,
                "social_links": json.dumps(socials),
                "scraped_email": email,
                "raw_html": html[:25000] # Increased limit for LLM processing
            }
    except Exception as e:
        print(f"Scraping error for {url}: {e}")
        return {}

def generate_ai_summary(name: str, type: str, description: str) -> str:
    """Generate AI summary using OpenRouter."""
    api_key = get_api_key()
    if not api_key:
        if not description:
            return f"{name} is a {type} located in this area."
        return f"{name} ({type}): {description[:150]}..."

    prompt = f"Summarize this business in one short sentence: Name: {name}, Type: {type}, Description: {description}"
    summary = call_openrouter(prompt)
    return summary.strip() if summary else f"{name} is a {type}."

def html_to_markdown(html: str) -> str:
    """Convert HTML to clean markdown to save tokens."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_tables = False
    return h.handle(html)

def extract_data_with_llm(html: str, fields: List[str]) -> Dict[str, Any]:
    """Use LLM to extract structured data from HTML, optimized with Markdown and schema enforcement."""
    api_key = get_api_key()
    if not api_key:
        return {}

    # Optimize: Convert to markdown to save significantly on tokens
    content = html_to_markdown(html)

    schema_example = json.dumps({
        "businesses": [
            {f: "example_value" for f in fields}
        ]
    })

    prompt = f"""
    Task: Extract structured business data from the following webpage content.
    Return ONLY a valid JSON object. Do not include any conversational text or explanations.

    Schema:
    {schema_example}

    Content (Markdown):
    {content[:15000]}
    """

    result = call_openrouter(prompt)
    if not result:
        return {}

    try:
        # Robust JSON extraction: look for the first '{' and last '}'
        json_start = result.find('{')
        json_end = result.rfind('}') + 1
        if json_start == -1 or json_end == 0:
             return {}

        json_str = result[json_start:json_end]
        data = json.loads(json_str)

        # Simple validation: ensure 'businesses' key exists and is a list
        if "businesses" not in data or not isinstance(data["businesses"], list):
            if isinstance(data, list): # LLM might return a list directly
                return {"businesses": data}
            return {"businesses": []}

        return data
    except Exception as e:
        print(f"Error parsing LLM extraction JSON: {e}")
        return {}
