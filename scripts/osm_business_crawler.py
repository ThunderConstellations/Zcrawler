#!/usr/bin/env python3
"""Fetch businesses from OSM and sort by distance to a reference address."""

from __future__ import annotations

import csv
import json
import math
import re
import time
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import argparse

USER_AGENT = "Zcrawler/1.0 (contact: local-run)"
REFERENCE_ADDRESS = "410 Glendale Blvd, Valparaiso, Indiana 46383"
CITY_QUERY = "Valparaiso, Indiana, USA"
OUTPUT_DIR = Path("output")
OUTPUT_JSON = OUTPUT_DIR / "businesses.json"
OUTPUT_CSV = OUTPUT_DIR / "businesses.csv"
OUTPUT_MD = OUTPUT_DIR / "businesses.md"
OUTPUT_IMPROVEMENTS_MD = OUTPUT_DIR / "crawler_improvements_applied.md"
REQUEST_TIMEOUT_SECONDS = 40
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
)
NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS = 1.1
MAX_REVERSE_GEOCODE_LOOKUPS = 30
SELECTED_CATEGORIES: List[str] = []
RADIUS_MI: Optional[float] = None

BUSINESS_AMENITY_VALUES = (
    "restaurant", "fast_food", "cafe", "bar", "pub", "bank", "atm", "clinic",
    "doctors", "dentist", "pharmacy", "hospital", "veterinary", "fuel",
    "cinema", "theatre", "marketplace", "car_rental", "car_wash", "car_repair",
    "hairdresser", "beauty",
)
BUSINESS_TOURISM_VALUES = ("hotel", "motel", "guest_house", "hostel")
BUSINESS_LEISURE_VALUES = ("fitness_centre", "sports_centre", "tanning_salon")
BUSINESS_KEYS = ("shop", "amenity", "office", "craft", "tourism", "leisure")
PHONE_SANITIZE_PATTERN = re.compile(r"[^\d+]")


@dataclass
# pylint: disable=too-many-instance-attributes
class Business:
    """Normalized business record returned by the crawler."""
    name: str
    business_type: str
    phone: str
    website: str
    email: str
    opening_hours: str
    location: str
    latitude: float
    longitude: float
    distance_miles: float
    quality_score: int
    source: str


def http_get_json(url: str) -> Dict:
    """Execute a GET request and parse JSON payload."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def http_post_json(url: str, payload: str) -> Dict:
    """Execute a POST request and parse JSON payload."""
    data = payload.encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def geocode_address(address: str) -> Tuple[float, float]:
    """Return latitude and longitude for a human-readable address."""
    params = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    payload = http_get_json(url)
    if not payload:
        raise RuntimeError(f"Could not geocode address: {address}")
    time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
    return float(payload[0]["lat"]), float(payload[0]["lon"])


def find_city_area_id(city_query: str) -> int:
    """Resolve an OSM relation area ID for a city query."""
    params = urllib.parse.urlencode({"q": city_query, "format": "jsonv2", "limit": 5})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    payload = http_get_json(url)
    for item in payload:
        osm_type = item.get("osm_type")
        if osm_type == "relation":
            time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
            return 3600000000 + int(item["osm_id"])
    raise RuntimeError(f"Could not find relation area for city: {city_query}")


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance between two points in miles."""
    radius_miles = 3958.7613
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_miles * c


def overpass_business_query(area_id: int, lat: Optional[float] = None, lon: Optional[float] = None) -> str:
    """Build the Overpass query for business-like features in an area or around a point."""

    scope = f"area({area_id})"
    if RADIUS_MI and lat is not None and lon is not None:
        # Convert miles to meters for Overpass
        radius_meters = RADIUS_MI * 1609.34
        scope = f"around:{radius_meters:.1f},{lat:.6f},{lon:.6f}"

    if SELECTED_CATEGORIES:
        pattern = "|".join(SELECTED_CATEGORIES)
        return f"""
[out:json][timeout:120];
(
  nwr["shop"~"{pattern}"]({scope});
  nwr["amenity"~"{pattern}"]({scope});
  nwr["office"~"{pattern}"]({scope});
  nwr["craft"~"{pattern}"]({scope});
  nwr["tourism"~"{pattern}"]({scope});
  nwr["leisure"~"{pattern}"]({scope});
);
out center;
"""

    amenity_pattern = "|".join(BUSINESS_AMENITY_VALUES)
    tourism_pattern = "|".join(BUSINESS_TOURISM_VALUES)
    leisure_pattern = "|".join(BUSINESS_LEISURE_VALUES)
    return f"""
[out:json][timeout:120];
(
  nwr["shop"]({scope});
  nwr["office"]({scope});
  nwr["craft"]({scope});
  nwr["amenity"~"{amenity_pattern}"]({scope});
  nwr["tourism"~"{tourism_pattern}"]({scope});
  nwr["leisure"~"{leisure_pattern}"]({scope});
);
out center;
"""


def tag_value(tags: Dict, *keys: str) -> str:
    """Retrieve the first available value from a list of keys."""
    for key in keys:
        val = tags.get(key)
        if val:
            return str(val).strip()
    return ""


def normalize_phone(phone: str) -> str:
    """Strip non-digit characters from phone numbers."""
    if not phone:
        return "N/A"
    return PHONE_SANITIZE_PATTERN.sub("", phone) or "N/A"


def normalize_website(url: str) -> str:
    """Ensure website URLs have a protocol."""
    if not url:
        return "N/A"
    if not url.startswith(("http://", "https://")):
        return f"http://{url}"
    return url


def choose_business_type(tags: Dict) -> str:
    """Determine a friendly business type from various tags."""
    for key in BUSINESS_KEYS:
        val = tags.get(key)
        if val:
            return str(val).replace("_", " ").title()
    return "Business"


def format_location(tags: Dict, lat: float, lon: float) -> str:
    """Format a human-readable location string from tags or coordinates."""
    addr = []
    street = tags.get("addr:street")
    house = tags.get("addr:housenumber")
    if street:
        addr.append(f"{house} {street}".strip() if house else street)
    city = tags.get("addr:city")
    if city:
        addr.append(city)
    if not addr:
        return f"{lat:.6f}, {lon:.6f}"
    return ", ".join(addr)


def quality_score(phone: str, website: str, location: str, hours: str) -> int:
    """Calculate a data quality score based on present fields."""
    score = 0
    if phone != "N/A": score += 25
    if website != "N/A": score += 25
    if hours != "N/A": score += 25
    if not re.match(r"^-?\d+\.\d+", location): score += 25
    return score


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Perform a reverse-geocode lookup via Nominatim."""
    params = urllib.parse.urlencode({
        "lat": lat, "lon": lon, "format": "jsonv2", "zoom": 18, "addressdetails": 1
    })
    url = f"https://nominatim.openstreetmap.org/reverse?{params}"
    try:
        payload = http_get_json(url)
        time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
        addr = payload.get("address", {})
        parts = []
        if addr.get("house_number"): parts.append(addr["house_number"])
        if addr.get("road"): parts.append(addr["road"])
        if addr.get("city") or addr.get("town"): parts.append(addr.get("city") or addr["town"])
        return ", ".join(parts) if parts else None
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


def enrich_missing_locations(businesses: List[Business]) -> None:
    """Perform limited reverse-geocoding for nearest records missing addresses."""
    lookups = 0
    for business in businesses:
        if lookups >= MAX_REVERSE_GEOCODE_LOOKUPS:
            break
        if not re.search(r"[a-zA-Z]", business.location):
            resolved = reverse_geocode(business.latitude, business.longitude)
            if resolved:
                business.location = resolved
            lookups += 1


def extract_businesses(elements: Iterable[Dict], reference_lat: float, reference_lon: float) -> List[Business]:
    """Convert raw OSM elements into deduplicated, sorted business rows."""
    dedup: Dict[Tuple[str, str, str], Business] = {}
    for item in elements:
        tags = item.get("tags", {})
        lat = item.get("lat", item.get("center", {}).get("lat"))
        lon = item.get("lon", item.get("center", {}).get("lon"))
        if lat is None or lon is None: continue
        name = tag_value(tags, "name", "brand")
        if not name: continue
        phone = normalize_phone(tag_value(tags, "phone", "contact:phone"))
        website = normalize_website(tag_value(tags, "website", "contact:website"))
        email = tag_value(tags, "email", "contact:email") or "N/A"
        opening_hours = tags.get("opening_hours", "").strip() or "N/A"
        business_type = choose_business_type(tags)
        location = format_location(tags, float(lat), float(lon))
        distance = haversine_miles(reference_lat, reference_lon, float(lat), float(lon))
        score = quality_score(phone, website, location, opening_hours)
        source = f"{item.get('type', 'nwr')}:{item.get('id', 'unknown')}"
        business = Business(
            name=name, business_type=business_type, phone=phone, website=website,
            email=email, opening_hours=opening_hours, location=location,
            latitude=float(lat), longitude=float(lon), distance_miles=distance,
            quality_score=score, source=source
        )
        dedup_key = (business.name.lower(), business.location.lower(), business.business_type.lower())
        existing = dedup.get(dedup_key)
        if existing is None or business.quality_score > existing.quality_score:
            dedup[dedup_key] = business
    results = list(dedup.values())
    results.sort(key=lambda item: (item.distance_miles, -item.quality_score, item.name.lower()))
    return results


def write_outputs(businesses: List[Business], reference_lat: float, reference_lon: float) -> None:
    """Persist business results to JSON, CSV, and Markdown files."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_payload = {
        "reference_address": REFERENCE_ADDRESS,
        "reference_latitude": reference_lat,
        "reference_longitude": reference_lon,
        "generated_at_unix": int(time.time()),
        "count": len(businesses),
        "businesses": [business.__dict__ for business in businesses],
    }
    OUTPUT_JSON.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["distance_miles", "name", "business_type", "phone", "website", "email", "opening_hours", "location", "latitude", "longitude", "quality_score", "source"])
        for b in businesses:
            writer.writerow([f"{b.distance_miles:.2f}", b.name, b.business_type, b.phone, b.website, b.email, b.opening_hours, b.location, f"{b.latitude:.6f}", f"{b.longitude:.6f}", b.quality_score, b.source])

    lines = ["# Business Findings (Sorted by Distance)", "", f"Reference address: **{REFERENCE_ADDRESS}**", f"Reference coordinates: `{reference_lat:.6f}, {reference_lon:.6f}`", f"Total businesses found: **{len(businesses)}**", "", "| # | Distance (mi) | Name | Type | Phone | Website | Location | Score |", "|---|---------------|------|------|-------|---------|----------|-------|"]
    for index, b in enumerate(businesses, start=1):
        website_cell = f"[Link]({b.website})" if b.website.startswith("http") else "N/A"
        lines.append(f"| {index} | {b.distance_miles:.2f} | {b.name.replace('|', ' ')} | {b.business_type.replace('|', ' ')} | {b.phone.replace('|', ' ')} | {website_cell} | {b.location.replace('|', ' ')} | {b.quality_score} |")
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def crawl_businesses() -> List[Business]:
    """Crawl businesses and save sorted outputs."""
    reference_lat, reference_lon = geocode_address(REFERENCE_ADDRESS)
    city_area_id = find_city_area_id(CITY_QUERY)
    overpass_query = overpass_business_query(city_area_id, reference_lat, reference_lon)
    overpass_payload = urllib.parse.urlencode({"data": overpass_query})
    response: Optional[Dict] = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            response = http_post_json(endpoint, overpass_payload)
            break
        except Exception:
            continue
    if response is None:
        raise RuntimeError("Failed querying Overpass endpoints")
    elements = response.get("elements", [])
    businesses = extract_businesses(elements, reference_lat, reference_lon)
    enrich_missing_locations(businesses)
    write_outputs(businesses, reference_lat, reference_lon)
    return businesses


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="OSM business crawler.")
    parser.add_argument("--reference-address", default=REFERENCE_ADDRESS)
    parser.add_argument("--city-query", default=CITY_QUERY)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--user-agent", default=USER_AGENT)
    parser.add_argument("--no-reverse-geocode", action="store_true")
    parser.add_argument("--max-reverse-geocode-lookups", type=int, default=MAX_REVERSE_GEOCODE_LOOKUPS)
    parser.add_argument("--categories", help="Comma-separated categories to filter by (e.g. cafe,restaurant)")
    parser.add_argument("--radius-mi", type=float, help="Radius in miles around reference address for search.")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()
    global USER_AGENT, REFERENCE_ADDRESS, CITY_QUERY, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_CSV, OUTPUT_MD, MAX_REVERSE_GEOCODE_LOOKUPS, SELECTED_CATEGORIES, RADIUS_MI
    USER_AGENT = args.user_agent
    REFERENCE_ADDRESS = args.reference_address
    CITY_QUERY = args.city_query
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_JSON = OUTPUT_DIR / "businesses.json"
    OUTPUT_CSV = OUTPUT_DIR / "businesses.csv"
    OUTPUT_MD = OUTPUT_DIR / "businesses.md"
    MAX_REVERSE_GEOCODE_LOOKUPS = 0 if args.no_reverse_geocode else args.max_reverse_geocode_lookups
    RADIUS_MI = args.radius_mi
    if args.categories:
        SELECTED_CATEGORIES = [c.strip() for c in args.categories.split(",") if c.strip()]
    businesses = crawl_businesses()
    print(f"Wrote {len(businesses)} businesses to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
