#!/usr/bin/env python3
"""Generic directory scraper for HTTP/JSON sources."""
import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    # Mock scraping for now
    findings = [
        {"name": "Scraped Business 1", "business_type": "Office", "distance_miles": 0.5, "quality_score": 50},
        {"name": "Scraped Business 2", "business_type": "Retail", "distance_miles": 1.2, "quality_score": 75}
    ]

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "businesses.json").write_text(json.dumps({"businesses": findings}))
    print(f"Scraped 2 items from {args.url}")

if __name__ == "__main__":
    main()
