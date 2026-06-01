import re
import urllib.request
from typing import Dict, List, Optional
import json

def extract_basic_info_from_url(url: str) -> Dict[str, str]:
    """Scrape website meta tags for description and look for social links."""
    if not url or url == "N/A":
        return {}

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'})
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')

            # Find description (standard and OpenGraph)
            description = ""
            patterns = [
                r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']',
                r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']description["\']',
            ]
            for p in patterns:
                m = re.search(p, html, re.I)
                if m:
                    description = m.group(1)
                    break

            # Find title
            title = ""
            t_match = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
            if t_match:
                title = t_match.group(1).strip()

            # Look for common social links
            socials = {}
            for platform in ['facebook', 'instagram', 'twitter', 'linkedin']:
                pattern = f'href=["\'](https?://(www\.)?{platform}\.com/[^"\']+)["\']'
                m = re.search(pattern, html, re.I)
                if m:
                    socials[platform] = m.group(1)

            # Try to find an email
            email = ""
            email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', html)
            if email_match:
                email = email_match.group(0)

            return {
                "description": description,
                "title": title,
                "social_links": json.dumps(socials),
                "scraped_email": email
            }
    except Exception:
        return {}

def generate_ai_summary(name: str, type: str, description: str) -> str:
    """Mock AI summary generation."""
    if not description:
        return f"{name} is a {type} located in this area."
    return f"{name} ({type}): {description[:150]}..."
