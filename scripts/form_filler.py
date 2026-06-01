#!/usr/bin/env python3
"""AI-powered form autofiller using Playwright."""
import asyncio
import argparse
import json
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.append(str(Path(__file__).resolve().parents[1]))
from webapp.app.enrichment import call_openrouter

async def fill_form(url: str, user_profile: dict, headless: bool = True):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        page = await browser.new_page()

        print(f"Navigating to form: {url}...")
        await page.goto(url, wait_until="networkidle")

        # Extract form fields
        fields = await page.evaluate("""() => {
            const inputs = Array.from(document.querySelectorAll('input, select, textarea'));
            return inputs.map(i => ({
                id: i.id,
                name: i.name,
                type: i.type,
                placeholder: i.placeholder,
                label: document.querySelector(`label[for="${i.id}"]`)?.innerText || '',
                value: i.value
            }));
        }""")

        print(f"Found {len(fields)} fields. Consulting LLM for values...")

        prompt = f"""
        Given the following form fields and user profile, return a JSON mapping of field 'name' or 'id' to the value that should be filled.

        Fields:
        {json.dumps(fields, indent=2)}

        User Profile:
        {json.dumps(user_profile, indent=2)}

        Return only the JSON mapping.
        """

        fill_plan_str = call_openrouter(prompt)
        if not fill_plan_str:
            print("Failed to get fill plan from LLM.")
            await browser.close()
            return

        try:
            fill_plan = json.loads(fill_plan_str.strip('`').replace('json', ''))
        except Exception as e:
            print(f"Error parsing fill plan: {e}")
            await browser.close()
            return

        print("Filling form...")
        for field in fields:
            key = field['name'] or field['id']
            if key in fill_plan:
                val = fill_plan[key]
                print(f"Filling {key} with {val}")
                try:
                    if field['type'] == 'select-one':
                        await page.select_option(f"#{field['id']}" if field['id'] else f"[name='{field['name']}']", value=str(val))
                    else:
                        await page.fill(f"#{field['id']}" if field['id'] else f"[name='{field['name']}']", str(val))
                except Exception as e:
                    print(f"Could not fill {key}: {e}")

        print("Form filled. Waiting for user to review...")
        await asyncio.sleep(10)
        await browser.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    profile = json.loads(Path(args.profile_json).read_text())
    asyncio.run(fill_form(args.url, profile, headless=not args.headful))

if __name__ == "__main__":
    main()
