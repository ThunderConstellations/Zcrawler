import re
import json
import os
import time
import base64
import httpx
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
import html2text
from dotenv import load_dotenv
from webapp.app.db import SessionLocal
from webapp.app.models import SystemSetting

load_dotenv()

def get_api_key():
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        try:
            with SessionLocal() as db:
                setting = db.get(SystemSetting, "OPENROUTER_API_KEY")
                if setting: key = setting.value
        except Exception: pass
    return key

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

def call_openrouter(prompt: str, model: str = "google/gemini-2.0-flash-001", retries: int = 3) -> Optional[str]:
    api_key = get_api_key()
    if not api_key: return None
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://github.com/yourusername/Zcrawler", "X-Title": "Zcrawler"}
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(retries):
        try:
            with httpx.Client() as client:
                response = client.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60.0)
                if response.status_code == 429:
                     time.sleep((attempt + 1) * 5)
                     continue
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"OpenRouter Error: {e}")
            if attempt < retries - 1: time.sleep(2 ** attempt)
    return None

def extract_basic_info_from_url(url: str) -> Dict[str, str]:
    if not url or url == "N/A": return {}
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        with httpx.Client(headers=headers, follow_redirects=True) as client:
            response = client.get(url, timeout=15.0)
            response.raise_for_status()
            html = response.text
            soup = BeautifulSoup(html, 'html.parser')
            description = ""
            desc_tag = soup.find('meta', attrs={'name': 'description'}) or soup.find('meta', attrs={'property': 'og:description'})
            if desc_tag: description = desc_tag.get('content', '')
            title = soup.title.string.strip() if soup.title else ""
            socials = {}
            for platform in ['facebook', 'instagram', 'twitter', 'linkedin']:
                link = soup.find('a', href=re.compile(rf'{platform}\.com', re.I))
                if link: socials[platform] = link['href']
            email = ""
            email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html)
            if email_match: email = email_match.group(0)
            return {"description": description, "title": title, "social_links": json.dumps(socials), "scraped_email": email, "raw_html": html[:30000]}
    except Exception: return {}

def generate_ai_summary(name: str, type: str, description: str) -> str:
    prompt = f"Summarize this business in one concise, futuristic-sounding sentence: Name: {name}, Type: {type}, Description: {description}"
    summary = call_openrouter(prompt)
    return summary.strip() if summary else f"{name} is a {type}."

def analyze_sentiment(text: str) -> str:
    if not text: return "Neutral"
    prompt = f"Analyze sentiment and return ONLY 'Positive', 'Neutral', or 'Negative': {text[:2000]}"
    res = call_openrouter(prompt)
    if res:
        r = res.strip().lower()
        if "positive" in r: return "Positive"
        if "negative" in r: return "Negative"
    return "Neutral"

def clean_data_with_ai(data_json: str) -> str:
    prompt = f"Clean and format this business data JSON into a high-fidelity standard. Return ONLY JSON: {data_json}"
    res = call_openrouter(prompt)
    return res or data_json

def evaluate_semantic_change(old_data: str, new_data: str, alert_query: str) -> Optional[str]:
    prompt = f"Compare datasets. Query: {alert_query}. Old: {old_data}. New: {new_data}. If significant change, explain shortly, else 'NO'."
    res = call_openrouter(prompt)
    if res and "NO" not in res.upper(): return res.strip()
    return None

def vision_extract_from_image(image_path: str, prompt: str) -> Optional[str]:
    api_key = get_api_key()
    if not api_key or not os.path.exists(image_path): return "Neural Vision processing unavailable: missing artifact."
    with open(image_path, "rb") as f: base64_image = base64.b64encode(f.read()).decode('utf-8')
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "google/gemini-2.0-flash-001", "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]}
    try:
        with httpx.Client() as client:
            response = client.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60.0)
            return response.json()["choices"][0]["message"]["content"]
    except: return "Vision inference cycle failed."

def extract_salary_range(html: str) -> str:
    match = re.search(r'\$[0-9,]+.*-.*\$[0-9,]+', html)
    if match: return match.group(0)
    prompt = f"Extract salary range from this HTML. Return ONLY the range or 'Not specified': {html[:5000]}"
    return call_openrouter(prompt) or "Not specified"

def parse_resume_with_ai(text: str) -> Dict[str, Any]:
    prompt = f"Parse resume and return valid JSON with full_name, email, phone, skills, work_experience, summary: {text[:15000]}"
    res = call_openrouter(prompt)
    if res:
        try:
            start = res.find('{')
            end = res.rfind('}') + 1
            return json.loads(res[start:end])
        except: pass
    return {}

def analyze_error_with_ai(log_tail: str, error_msg: str) -> str:
    prompt = f"Analyze error for non-technical user. Suggest one-click fix. Error: {error_msg}. Log: {log_tail}"
    return call_openrouter(prompt) or "System identifies a potential layout shift or network variance. Verify source URL."


def find_referral_contacts(html: str, profile_referrals: list) -> List[str]:
    """Search HTML for common contacts or companies matching user's referral network."""
    found = []
    for ref in profile_referrals:
        if ref['company'].lower() in html.lower():
            found.append(f"{ref['name']} ({ref['company']})")
    return found
