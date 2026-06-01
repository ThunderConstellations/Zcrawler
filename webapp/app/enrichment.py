import re
import json
import os
import httpx
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def call_openrouter(prompt: str, model: str = "google/gemini-2.0-flash-001") -> Optional[str]:
    """Call OpenRouter API with a prompt."""
    if not OPENROUTER_API_KEY:
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/yourusername/Zcrawler", # Required by OpenRouter
        "X-Title": "Zcrawler"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        with httpx.Client() as client:
            response = client.post(OPENROUTER_URL, headers=headers, json=payload, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"OpenRouter API error: {e}")
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
    if not OPENROUTER_API_KEY:
        if not description:
            return f"{name} is a {type} located in this area."
        return f"{name} ({type}): {description[:150]}..."

    prompt = f"Summarize this business in one short sentence: Name: {name}, Type: {type}, Description: {description}"
    summary = call_openrouter(prompt)
    return summary.strip() if summary else f"{name} is a {type}."

def extract_data_with_llm(html: str, fields: List[str]) -> Dict[str, Any]:
    """Use LLM to extract structured data from HTML."""
    if not OPENROUTER_API_KEY:
        return {}

    prompt = f"Extract the following fields from this HTML and return a JSON object with a 'businesses' key containing a list of objects. Fields: {', '.join(fields)}\n\nHTML:\n{html[:20000]}"
    result = call_openrouter(prompt)
    if not result:
        return {}

    try:
        # Clean up JSON if LLM returned it in markdown blocks
        json_str = re.sub(r'```json\n|\n```', '', result).strip()
        return json.loads(json_str)
    except Exception:
        return {}
