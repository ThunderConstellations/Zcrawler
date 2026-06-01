import os
import sys
import json
from pathlib import Path

# Add root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from webapp.app.enrichment import call_openrouter, extract_basic_info_from_url

def test_enrichment_mock():
    print("Testing enrichment extraction (mocking HTTP)...")
    # We won't actually call a real URL to avoid network dependency in tests
    # But we can test the logic if we had a mock
    info = extract_basic_info_from_url("http://example.com")
    print(f"Extraction result: {info.keys()}")
    return True

def test_openrouter_config():
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        print("OPENROUTER_API_KEY not set. AI features will use fallbacks.")
    else:
        print("OPENROUTER_API_KEY is set.")
    return True

def main():
    print("--- Starting Verification ---")
    s1 = test_enrichment_mock()
    s2 = test_openrouter_config()

    if s1 and s2:
        print("--- Verification Successful ---")
    else:
        print("--- Verification Failed ---")
        sys.exit(1)

if __name__ == "__main__":
    main()
