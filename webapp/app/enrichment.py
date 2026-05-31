import re
import urllib.request
from typing import Dict, List, Optional
import json

def extract_basic_info_from_url(url: str) -> Dict[str, str]:
    """Scrape website meta tags for description and look for social links."""
    if not url or url == "N/A":
        return {}

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')

            # Find description
            desc_match = re.search(r'<meta name="description" content="([^"]+)"', html, re.I)
            description = desc_match.group(1) if desc_match else ""

            # Look for common social links
            socials = {}
            for platform in ['facebook', 'instagram', 'twitter', 'linkedin']:
                pattern = f'href="(https?://(www\.)?{platform}\.com/[^"]+)"'
                m = re.search(pattern, html, re.I)
                if m:
                    socials[platform] = m.group(1)

            return {
                "description": description,
                "social_links": json.dumps(socials)
            }
    except Exception:
        return {}

def generate_ai_summary(name: str, type: str, description: str) -> str:
    """Mock AI summary generation."""
    if not description:
        return f"{name} is a {type} located in this area."
    return f"{name} is a {type}. Online description: {description[:100]}..."
