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
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
)
NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS = 1.1
MAX_REVERSE_GEOCODE_LOOKUPS = 10
SELECTED_CATEGORIES: List[str] = []
RADIUS_MI: Optional[float] = None
RESULT_LIMIT: Optional[int] = None

@dataclass
class Business:
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
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))

def http_post_json(url: str, payload: str) -> Dict:
    data = payload.encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.loads(response.read().decode("utf-8"))

def retry_http_post_json(url: str, payload: str, retries: int = 3) -> Optional[Dict]:
    for i in range(retries):
        try:
            return http_post_json(url, payload)
        except (HTTPError, URLError, TimeoutError) as e:
            print(f"Attempt {i+1} failed for {url}: {e}")
            if i < retries - 1:
                time.sleep(2 ** i) # Exponential backoff
    return None


def geocode_address(address: str) -> Tuple[float, float]:
    # Check if address is already coordinates
    coord_match = re.match(r"^([-+]?\d+\.\d+),\s*([-+]?\d+\.\d+)$", address)
    if coord_match:
        return float(coord_match.group(1)), float(coord_match.group(2))

    params = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1})

    params = urllib.parse.urlencode({"q": address, "format": "jsonv2", "limit": 1})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    payload = http_get_json(url)
    if not payload: raise RuntimeError(f"Could not geocode address: {address}")
    time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
    return float(payload[0]["lat"]), float(payload[0]["lon"])

def find_city_area_id(city_query: str) -> int:
    params = urllib.parse.urlencode({"q": city_query, "format": "jsonv2", "limit": 5})
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    payload = http_get_json(url)
    for item in payload:
        if item.get("osm_type") == "relation":
            time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
            return 3600000000 + int(item["osm_id"])
    raise RuntimeError(f"Could not find relation area for city: {city_query}")

def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi, d_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2)**2
    return radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def overpass_business_query(area_id: int, lat: float, lon: float) -> str:
    if RADIUS_MI:
        radius_meters = RADIUS_MI * 1609.34
        scope = f"around:{radius_meters:.1f},{lat:.6f},{lon:.6f}"
    else:
        scope = f"area:{area_id}"

    if SELECTED_CATEGORIES:
        pattern = "|".join(SELECTED_CATEGORIES)
        return f'[out:json][timeout:120];(nwr["shop"~"{pattern}"]({scope});nwr["amenity"~"{pattern}"]({scope});nwr["office"~"{pattern}"]({scope});nwr["craft"~"{pattern}"]({scope});nwr["tourism"~"{pattern}"]({scope});nwr["leisure"~"{pattern}"]({scope}););out center;'

    amenities = "restaurant|fast_food|cafe|bar|pub|bank|atm|clinic|doctors|dentist|pharmacy|hospital|veterinary|fuel|cinema|theatre|marketplace|car_rental|car_wash|car_repair|hairdresser|beauty"
    tourism = "hotel|motel|guest_house|hostel"
    leisure = "fitness_centre|sports_centre|tanning_salon"

    return f"""[out:json][timeout:120];
(
  nwr["shop"]({scope});
  nwr["office"]({scope});
  nwr["craft"]({scope});
  nwr["amenity"~"{amenities}"]({scope});
  nwr["tourism"~"{tourism}"]({scope});
  nwr["leisure"~"{leisure}"]({scope});
);
out center;"""

def tag_value(tags: Dict, *keys: str) -> str:
    for key in keys:
        if tags.get(key): return str(tags[key]).strip()
    return ""

def normalize_phone(phone: str) -> str:
    return re.sub(r"[^\d+]", "", phone) if phone else "N/A"

def normalize_website(url: str) -> str:
    if not url: return "N/A"
    return url if url.startswith("http") else f"http://{url}"

def choose_business_type(tags: Dict) -> str:
    for key in ("shop", "amenity", "office", "craft", "tourism", "leisure"):
        if tags.get(key): return str(tags[key]).replace("_", " ").title()
    return "Business"

def format_location(tags: Dict, lat: float, lon: float) -> str:
    addr = []
    if tags.get("addr:street"):
        s = tags["addr:street"]
        h = tags.get("addr:housenumber", "")
        addr.append(f"{h} {s}".strip())
    if tags.get("addr:city"): addr.append(tags["addr:city"])
    return ", ".join(addr) if addr else f"{lat:.6f}, {lon:.6f}"

def quality_score(phone: str, website: str, location: str, hours: str) -> int:
    score = 0
    if phone != "N/A": score += 25
    if website != "N/A": score += 25
    if hours != "N/A": score += 25
    if re.search(r"[a-zA-Z]", location): score += 25
    return score

def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=jsonv2&zoom=18&addressdetails=1"
        payload = http_get_json(url)
        time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
        a = payload.get("address", {})
        parts = [v for k, v in a.items() if k in ("house_number", "road", "city", "town")]
        return ", ".join(parts) if parts else None
    except Exception: return None

def enrich_missing_locations(businesses: List[Business]) -> None:
    lookups = 0
    for b in businesses:
        if lookups >= MAX_REVERSE_GEOCODE_LOOKUPS: break
        if not re.search(r"[a-zA-Z]", b.location):
            res = reverse_geocode(b.latitude, b.longitude)
            if res: b.location = res
            lookups += 1

def extract_businesses(elements: Iterable[Dict], ref_lat: float, ref_lon: float) -> List[Business]:
    dedup: Dict[Tuple[str, str], Business] = {}
    for item in elements:
        tags = item.get("tags", {})
        lat = item.get("lat", item.get("center", {}).get("lat"))
        lon = item.get("lon", item.get("center", {}).get("lon"))
        if lat is None or lon is None or not tag_value(tags, "name", "brand"): continue

        name = tag_value(tags, "name", "brand")
        b = Business(
            name=name, business_type=choose_business_type(tags),
            phone=normalize_phone(tag_value(tags, "phone", "contact:phone")),
            website=normalize_website(tag_value(tags, "website", "contact:website")),
            email=tag_value(tags, "email", "contact:email") or "N/A",
            opening_hours=tags.get("opening_hours", "N/A"),
            location=format_location(tags, float(lat), float(lon)),
            latitude=float(lat), longitude=float(lon),
            distance_miles=haversine_miles(ref_lat, ref_lon, float(lat), float(lon)),
            quality_score=0, source=f"{item.get('type')}:{item.get('id')}"
        )
        b.quality_score = quality_score(b.phone, b.website, b.location, b.opening_hours)
        key = (b.name.lower(), b.location.lower())
        if key not in dedup or b.quality_score > dedup[key].quality_score: dedup[key] = b

    results = sorted(dedup.values(), key=lambda x: (x.distance_miles, -x.quality_score))
    return results[:RESULT_LIMIT] if RESULT_LIMIT else results

def write_outputs(businesses: List[Business]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_payload = {"reference_address": REFERENCE_ADDRESS, "generated_at": int(time.time()), "businesses": [b.__dict__ for b in businesses]}
    OUTPUT_JSON.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
    with OUTPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["distance", "name", "type", "phone", "website", "location", "score"])
        for b in businesses: w.writerow([f"{b.distance_miles:.2f}", b.name, b.business_type, b.phone, b.website, b.location, b.quality_score])

def main() -> None:
    global REFERENCE_ADDRESS, CITY_QUERY, OUTPUT_DIR, OUTPUT_JSON, OUTPUT_CSV, SELECTED_CATEGORIES, RADIUS_MI, RESULT_LIMIT, MAX_REVERSE_GEOCODE_LOOKUPS

    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-address", default=REFERENCE_ADDRESS)
    parser.add_argument("--city-query", default=CITY_QUERY)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--categories")
    parser.add_argument("--radius-mi", type=float)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-reverse-geocode-lookups", type=int, default=MAX_REVERSE_GEOCODE_LOOKUPS)
    parser.add_argument("--no-reverse-geocode", action="store_true")
    args = parser.parse_args()

    REFERENCE_ADDRESS, CITY_QUERY, RADIUS_MI, RESULT_LIMIT = args.reference_address, args.city_query, args.radius_mi, args.limit
    MAX_REVERSE_GEOCODE_LOOKUPS = args.max_reverse_geocode_lookups
    if args.no_reverse_geocode:
        MAX_REVERSE_GEOCODE_LOOKUPS = 0
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_JSON, OUTPUT_CSV = OUTPUT_DIR / "businesses.json", OUTPUT_DIR / "businesses.csv"
    if args.categories: SELECTED_CATEGORIES = [c.strip() for c in args.categories.split(",") if c.strip()]

    try:
        ref_lat, ref_lon = geocode_address(REFERENCE_ADDRESS)
    except Exception as e:
        print(f"Error geocoding reference address: {e}")
        return

    try:
        area_id = find_city_area_id(CITY_QUERY)
    except Exception as e:
        print(f"Error finding city area: {e}")
        return

    q = overpass_business_query(area_id, ref_lat, ref_lon)

    resp = None
    for e in OVERPASS_ENDPOINTS:
        resp = retry_http_post_json(e, urllib.parse.urlencode({"data": q}))
        if resp: break

    if not resp: raise RuntimeError("Overpass failed on all endpoints")
    businesses = extract_businesses(resp.get("elements", []), ref_lat, ref_lon)
    enrich_missing_locations(businesses)
    write_outputs(businesses)
    print(f"Wrote {len(businesses)} businesses to {OUTPUT_DIR}")

if __name__ == "__main__": main()
