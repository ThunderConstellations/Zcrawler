#!/usr/bin/env python3
"""AI-powered form autofiller using Playwright with Bot Stealth."""
import asyncio
import argparse
import json
import sys
import os
import random
import time
from pathlib import Path
from playwright.async_api import async_playwright

sys.path.append(str(Path(__file__).resolve().parents[1]))
from webapp.app.enrichment import call_openrouter

async def human_delay(min_s=0.5, max_s=2.0):
    await asyncio.sleep(random.uniform(min_s, max_s))

async def simulate_mouse_movement(page):
    viewport = page.viewport_size
    if viewport:
        # Move to a few random points
        for _ in range(random.randint(2, 5)):
            x, y = random.randint(0, viewport['width']), random.randint(0, viewport['height'])
            await page.mouse.move(x, y, steps=10)
            await asyncio.sleep(random.uniform(0.1, 0.4))

async def find_fields_with_ai(page, profile):
    """
    AI Vision Field Discovery Concept:
    Identify complex or hidden fields that standard selectors might miss.
    """
    print("🤖 AI Vision Field Discovery Initialized...")
    # In a real multimodal implementation, we'd take a screenshot and send it to Vision LLM
    # screenshot_path = "discovery_snapshot.png"
    # await page.screenshot(path=screenshot_path)
    # result = vision_extract_from_image(screenshot_path, "Find the labels and coordinates for all form fields.")
    return True

async def fill_form(url: str, user_profile: dict, headless: bool = True):
    async with async_playwright() as p:
        # Stealth: Use a realistic user agent
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"Navigating to form: {url}...")
        await page.goto(url, wait_until="networkidle")

        # Bot Stealth: Initial human-like interactions
        await human_delay(1, 3)
        await simulate_mouse_movement(page)
        await find_fields_with_ai(page, user_profile)

        # Detect ATS (Greenhouse, Lever, etc.)
        content = await page.content()
        is_greenhouse = "greenhouse.io" in content or "grnh.se" in content
        is_lever = "lever.co" in url or "lever.co" in content

        print(f"ATS Detected: {'Greenhouse' if is_greenhouse else 'Lever' if is_lever else 'Generic'}")

        # Extract form fields with better label association
        fields = await page.evaluate("""() => {
            const getLabel = (el) => {
                if (el.id) {
                    const label = document.querySelector(`label[for="${el.id}"]`);
                    if (label) return label.innerText.trim();
                }
                let parent = el.parentElement;
                while (parent && parent.tagName !== 'FORM') {
                    const labels = parent.querySelectorAll('label');
                    if (labels.length > 0) return labels[0].innerText.trim();
                    parent = parent.parentElement;
                }
                return "";
            };

            const inputs = Array.from(document.querySelectorAll('input, select, textarea, [role="combobox"]'));
            return inputs.map(i => {
                const rect = i.getBoundingClientRect();
                return {
                    id: i.id,
                    name: i.name,
                    type: i.type || i.getAttribute('role'),
                    placeholder: i.placeholder || i.getAttribute('placeholder'),
                    label: getLabel(i),
                    isVisible: rect.width > 0 && rect.height > 0
                };
            }).filter(f => f.type !== 'hidden' && f.isVisible);
        }""")

        print(f"Found {len(fields)} visible fields. Consulting LLM for values...")

        prompt = f\"\"\"
        As an expert job application assistant, map the following user profile to the detected form fields.

        Form Fields:
        {json.dumps(fields, indent=2)}

        User Profile:
        {json.dumps(user_profile, indent=2)}

        Instructions:
        1. Map profile fields (name, email, phone, linkedin, etc.) to form field IDs/names.
        2. For custom questions, use the 'summary' or 'work_experience' to draft a short answer.
        3. If a field asks for a resume, return 'UPLOAD_RESUME' as the value.
        4. Return a flat JSON object: {{"field_identifier": "value"}}.

        Return ONLY the JSON.
        \"\"\"

        fill_plan_str = call_openrouter(prompt)
        if not fill_plan_str:
            print("Failed to get fill plan from LLM.")
            await browser.close()
            return

        try:
            json_start = fill_plan_str.find('{')
            json_end = fill_plan_str.rfind('}') + 1
            fill_plan = json.loads(fill_plan_str[json_start:json_end])
        except Exception as e:
            print(f"Error parsing fill plan: {e}")
            await browser.close()
            return

        print("Executing fill plan...")
        for field in fields:
            key = field['id'] or field['name']
            if not key: continue

            value = fill_plan.get(field['id']) or fill_plan.get(field['name'])
            if not value: continue

            selector = f"#{field['id']}" if field['id'] else f"[name='{field['name']}']"

            try:
                # Stealth: Delay before each field
                await human_delay(0.2, 0.8)

                if value == "UPLOAD_RESUME":
                    resume_path = user_profile.get("resume_path")
                    if resume_path and os.path.exists(resume_path):
                        print(f"Uploading resume: {resume_path}")
                        await page.set_input_files(selector, resume_path)
                elif field['type'] == 'select-one' or field['type'] == 'select':
                    print(f"Selecting {value} for {key}")
                    await page.select_option(selector, label=str(value))
                elif field['type'] == 'checkbox' or field['type'] == 'radio':
                    if str(value).lower() in ['yes', 'true', '1']:
                        await page.check(selector)
                else:
                    print(f"Filling {key} with {value}")
                    # Stealth: Human-like typing
                    await page.type(selector, str(value), delay=random.randint(40, 120))
            except Exception as e:
                print(f"Error filling {key}: {e}")

        # Final Stealth Delay
        await human_delay(1, 2)

        output_path = f"form_filled_{int(time.time())}.png"
        await page.screenshot(path=output_path)
        print(f"Form filled successfully. Screenshot saved to {output_path}")

        if not headless:
            print("Holding for manual review (30s)...")
            await asyncio.sleep(30)

        await browser.close()

async def async_main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()

    profile_path = Path(args.profile_json)
    if not profile_path.exists():
        print(f"Profile not found: {args.profile_json}")
        return

    profile = json.loads(profile_path.read_text())
    await fill_form(args.url, profile, headless=not args.headful)

if __name__ == "__main__":
    asyncio.run(async_main())
