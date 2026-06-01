#!/usr/bin/env python3
"""Refined AI-powered form autofiller for ATS platforms like Greenhouse/Lever."""
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
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()

        print(f"Navigating to job application: {url}...")
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"Navigation failed: {e}")
            await browser.close()
            return

        # ATS Specific Tweaks
        if "greenhouse.io" in url:
            print("Detected Greenhouse ATS. Special handling engaged.")
            # Greenhouse often uses iframes for some parts, but usually the main form is direct.
        elif "lever.co" in url:
            print("Detected Lever ATS. Special handling engaged.")

        # 1. Extract interactive elements
        fields = await page.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll('input, select, textarea, [role="combobox"]'));
            return elements.map(i => {
                let labelText = '';
                // Try finding label by 'for' attribute
                if (i.id) {
                    const label = document.querySelector(`label[for="${i.id}"]`);
                    if (label) labelText = label.innerText;
                }
                // Try finding closest parent label
                if (!labelText) {
                    const parentLabel = i.closest('label');
                    if (parentLabel) labelText = parentLabel.innerText;
                }
                // Try finding label nearby
                if (!labelText) {
                    const prev = i.previousElementSibling;
                    if (prev && prev.tagName === 'LABEL') labelText = prev.innerText;
                }

                return {
                    id: i.id,
                    name: i.name,
                    type: i.type || i.getAttribute('role'),
                    placeholder: i.placeholder,
                    label: labelText.trim(),
                    tagName: i.tagName,
                    isVisible: i.offsetWidth > 0 && i.offsetHeight > 0
                };
            }).filter(f => f.isVisible && f.type !== 'hidden');
        }""")

        print(f"Found {len(fields)} visible fields.")

        # 2. Consult LLM for values
        prompt = f"""
        You are an expert at completing job applications. Map the user's profile to the following form fields found on a job page.

        Fields:
        {json.dumps(fields, indent=2)}

        User Profile:
        {json.dumps(user_profile, indent=2)}

        Rules:
        1. Return a JSON object mapping the field 'name' or 'id' (prefer 'id' if available) to the appropriate value from the profile.
        2. For 'file' types, provide the path to the resume if requested (e.g., "resume_path").
        3. If a field is a dropdown (select), provide the exact option text that matches best.
        4. Be intelligent about custom questions. If the profile doesn't have an exact answer, formulate a short, professional response based on the profile context.

        Return ONLY the JSON.
        """

        fill_plan_str = call_openrouter(prompt)
        if not fill_plan_str:
            print("Failed to get fill plan from LLM.")
            await browser.close()
            return

        try:
            # Strip markdown if LLM included it
            clean_json = fill_plan_str.strip()
            if clean_json.startswith("```json"): clean_json = clean_json[7:]
            if clean_json.endswith("```"): clean_json = clean_json[:-3]
            fill_plan = json.loads(clean_json)
        except Exception as e:
            print(f"Error parsing fill plan: {e}\nRaw response: {fill_plan_str}")
            await browser.close()
            return

        # 3. Apply the plan
        print("Applying fill plan...")
        for field in fields:
            key = field['id'] or field['name']
            if key in fill_plan:
                val = fill_plan[key]
                print(f"  -> Filling [{field['label'] or key}] with: {val}")
                try:
                    selector = f"#{field['id']}" if field['id'] else f"[name='{field['name']}']"
                    if field['tagName'] == 'SELECT' or field['type'] == 'select-one':
                        await page.select_option(selector, label=str(val))
                    elif field['type'] == 'file':
                        if os.path.exists(str(val)):
                            await page.set_input_files(selector, str(val))
                        else:
                            print(f"     ! File not found: {val}")
                    else:
                        await page.fill(selector, str(val))
                except Exception as e:
                    print(f"     ! Could not fill {key}: {e}")

        print("\nForm filled! Taking screenshot of result...")
        screenshot_path = "form_filled_preview.png"
        await page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")

        # Wait a bit for visibility if headful
        if not headless:
            await asyncio.sleep(5)

        await browser.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    try:
        profile = json.loads(Path(args.profile_json).read_text())
        asyncio.run(fill_form(args.url, profile, headless=not args.headful))
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
