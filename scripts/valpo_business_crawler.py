#!/usr/bin/env python3
"""Fetch businesses in Valparaiso, IN and sort by distance to a reference address."""

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
OUTPUT_JSON = OUTPUT_DIR / "valparaiso_businesses.json"
OUTPUT_CSV = OUTPUT_DIR / "valparaiso_businesses.csv"
OUTPUT_MD = OUTPUT_DIR / "valparaiso_businesses.md"
OUTPUT_IMPROVEMENTS_MD = OUTPUT_DIR / "crawler_improvements_applied.md"
REQUEST_TIMEOUT_SECONDS = 40
OVERPASS_ENDPOINTS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
)
NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS = 1.1
MAX_REVERSE_GEOCODE_LOOKUPS = 30

BUSINESS_AMENITY_VALUES = (
    "restaurant",
    "fast_food",
    "cafe",
    "bar",
    "pub",
    "bank",
    "atm",
    "clinic",
    "doctors",
    "dentist",
    "pharmacy",
    "hospital",
    "veterinary",
    "fuel",
    "cinema",
    "theatre",
    "marketplace",
    "car_rental",
    "car_wash",
    "car_repair",
    "hairdresser",
    "beauty",
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


def overpass_business_query(area_id: int) -> str:
    """Build the Overpass query for business-like features in an area."""
    amenity_pattern = "|".join(BUSINESS_AMENITY_VALUES)
    tourism_pattern = "|".join(BUSINESS_TOURISM_VALUES)
    leisure_pattern = "|".join(BUSINESS_LEISURE_VALUES)
    return f"""
[out:json][timeout:120];
area({area_id})->.searchArea;
(
  nwr["shop"](area.searchArea);
  nwr["office"](area.searchArea);
  nwr["craft"](area.searchArea);
  nwr["amenity"~"^({amenity_pattern})$"](area.searchArea);
  nwr["tourism"~"^({tourism_pattern})$"](area.searchArea);
  nwr["leisure"~"^({leisure_pattern})$"](area.searchArea);
);
out center tags;
""".strip()


def tag_value(tags: Dict[str, str], *keys: str) -> str:
    """Return first non-empty tag value from a key list."""

    for key in keys:
        value = tags.get(key)
        if value:
            return value.strip()
    return ""


def format_location(tags: Dict[str, str], lat: float, lon: float) -> str:
    """Create a readable location string from OSM tags or coordinates."""

    street = " ".join(
        filter(None, [tags.get("addr:housenumber", ""), tags.get("addr:street", "")])
    ).strip()
    city = tags.get("addr:city", "Valparaiso")
    state = tags.get("addr:state", "IN")
    postcode = tags.get("addr:postcode", "")
    parts = [street, city, state, postcode]
    readable = ", ".join([part for part in parts if part])
    if readable:
        return readable
    return f"{lat:.6f}, {lon:.6f}"


def choose_business_type(tags: Dict[str, str]) -> str:
    """Pick the first matching business-type tag."""

    for key in BUSINESS_KEYS:
        if key in tags and tags[key]:
            return f"{key}:{tags[key]}"
    return "unknown"


def normalize_phone(phone: str) -> str:
    """Normalize phone values for easier matching and readability."""

    if not phone:
        return "N/A"
    cleaned = PHONE_SANITIZE_PATTERN.sub("", phone)
    return cleaned if cleaned else phone


def normalize_website(website: str) -> str:
    """Normalize website values to a usable URL format."""

    if not website:
        return "N/A"
    url = website.strip()
    if not url:
        return "N/A"
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def quality_score(phone: str, website: str, location: str, opening_hours: str) -> int:
    """Compute a simple quality score for ranking records."""

    score = 0
    if phone != "N/A":
        score += 2
    if website != "N/A":
        score += 2
    if location and "," in location and not location.endswith("IN"):
        score += 2
    if opening_hours != "N/A":
        score += 1
    return score


def reverse_geocode(lat: float, lon: float) -> Optional[str]:
    """Reverse geocode coordinates to a best-effort address string."""

    params = urllib.parse.urlencode(
        {
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
            "format": "jsonv2",
            "addressdetails": 1,
            "zoom": 18,
        }
    )
    url = f"https://nominatim.openstreetmap.org/reverse?{params}"
    try:
        payload = http_get_json(url)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None
    finally:
        time.sleep(NOMINATIM_MIN_SECONDS_BETWEEN_REQUESTS)
    address = payload.get("address", {})
    house = address.get("house_number", "")
    road = address.get("road", "")
    city = address.get("city") or address.get("town") or address.get("village") or ""
    state = address.get("state", "")
    postcode = address.get("postcode", "")
    street = " ".join(filter(None, [house, road])).strip()
    parts = [street, city, state, postcode]
    readable = ", ".join([part for part in parts if part])
    return readable or None


def enrich_missing_locations(businesses: List[Business]) -> None:
    """Fill missing street addresses for top nearest records."""

    lookups = 0
    for business in businesses:
        if lookups >= MAX_REVERSE_GEOCODE_LOOKUPS:
            break
        if business.location.startswith("Valparaiso") or business.location.startswith(
            f"{business.latitude:.6f}"
        ):
            resolved = reverse_geocode(business.latitude, business.longitude)
            if resolved:
                business.location = resolved
            lookups += 1


def extract_businesses(
    elements: Iterable[Dict],
    reference_lat: float,
    reference_lon: float,
) -> List[Business]:
    """Convert raw OSM elements into deduplicated, sorted business rows."""
    # pylint: disable=too-many-locals

    dedup: Dict[Tuple[str, str, str], Business] = {}
    for item in elements:
        tags = item.get("tags", {})
        lat = item.get("lat", item.get("center", {}).get("lat"))
        lon = item.get("lon", item.get("center", {}).get("lon"))
        if lat is None or lon is None:
            continue

        name = tag_value(tags, "name", "brand")
        if not name:
            continue

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
            name=name,
            business_type=business_type,
            phone=phone,
            website=website,
            email=email,
            opening_hours=opening_hours,
            location=location,
            latitude=float(lat),
            longitude=float(lon),
            distance_miles=distance,
            quality_score=score,
            source=source,
        )
        dedup_key = (
            business.name.lower(),
            business.location.lower(),
            business.business_type.lower(),
        )
        existing = dedup.get(dedup_key)
        if existing is None or business.quality_score > existing.quality_score:
            dedup[dedup_key] = business

    results = list(dedup.values())
    results.sort(
        key=lambda item: (item.distance_miles, -item.quality_score, item.name.lower())
    )
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
        writer.writerow(
            [
                "distance_miles",
                "name",
                "business_type",
                "phone",
                "website",
                "email",
                "opening_hours",
                "location",
                "latitude",
                "longitude",
                "quality_score",
                "source",
            ]
        )
        for business in businesses:
            writer.writerow(
                [
                    f"{business.distance_miles:.2f}",
                    business.name,
                    business.business_type,
                    business.phone,
                    business.website,
                    business.email,
                    business.opening_hours,
                    business.location,
                    f"{business.latitude:.6f}",
                    f"{business.longitude:.6f}",
                    business.quality_score,
                    business.source,
                ]
            )

    lines = [
        "# Valparaiso, IN Businesses (Sorted by Distance)",
        "",
        f"Reference address: **{REFERENCE_ADDRESS}**",
        f"Reference coordinates: `{reference_lat:.6f}, {reference_lon:.6f}`",
        f"Total businesses found: **{len(businesses)}**",
        "",
        "| # | Distance (mi) | Name | Type | Phone | Website | Email | Hours | Location | Score |",
        "|---|---------------|------|------|-------|---------|-------|-------|----------|-------|",
    ]
    for index, business in enumerate(businesses, start=1):
        website = business.website
        if website.startswith(("http://", "https://")):
            website_cell = f"[Link]({website})"
        else:
            website_cell = "N/A"
        lines.append(
            f"| {index} | {business.distance_miles:.2f} | "
            f"{business.name.replace('|', ' ')} | "
            f"{business.business_type.replace('|', ' ')} | "
            f"{business.phone.replace('|', ' ')} | {website_cell} | "
            f"{business.email.replace('|', ' ')} | "
            f"{business.opening_hours.replace('|', ' ')} | "
            f"{business.location.replace('|', ' ')} | "
            f"{business.quality_score} |"
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    improvements = [
        "# Crawler Improvements Applied",
        "",
        "- Switched to business-focused Overpass filters for better signal quality.",
        "- Added contact enrichment fields: `email` and `opening_hours` when available.",
        "- Normalized phone and website values for cleaner output.",
        "- Added quality scoring so richer records rank higher within similar distances.",
        "- Added limited reverse-geocode enrichment for nearest records missing street addresses.",
        "- Preserved source IDs (`type:id`) for traceability and debugging.",
    ]
    OUTPUT_IMPROVEMENTS_MD.write_text("\n".join(improvements) + "\n", encoding="utf-8")


def crawl_valparaiso_businesses() -> List[Business]:
    """Crawl businesses in Valparaiso and save sorted outputs."""

    reference_lat, reference_lon = geocode_address(REFERENCE_ADDRESS)
    city_area_id = find_city_area_id(CITY_QUERY)
    overpass_query = overpass_business_query(city_area_id)
    overpass_payload = urllib.parse.urlencode({"data": overpass_query})
    response: Optional[Dict] = None
    last_error: Optional[BaseException] = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            response = http_post_json(endpoint, overpass_payload)
            break
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            last_error = exc
            try:
                params = urllib.parse.urlencode({"data": overpass_query})
                response = http_get_json(f"{endpoint}?{params}")
                break
            except (HTTPError, URLError, TimeoutError, ValueError) as nested_exc:
                last_error = nested_exc
                continue
    if response is None:
        raise RuntimeError(f"Failed querying Overpass endpoints: {last_error}")
    elements = response.get("elements", [])
    businesses = extract_businesses(elements, reference_lat, reference_lon)
    enrich_missing_locations(businesses)
    write_outputs(businesses, reference_lat, reference_lon)
    return businesses


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for webapp use."""

    parser = argparse.ArgumentParser(description="Valparaiso businesses crawler (OSM/Overpass).")
    parser.add_argument(
        "--reference-address",
        default=REFERENCE_ADDRESS,
        help="Reference address to sort by distance.",
    )
    parser.add_argument(
        "--city-query",
        default=CITY_QUERY,
        help="City query used for Nominatim area lookup (e.g., 'Valparaiso, Indiana, USA').",
    )
    parser.add_argument(
        "--output-dir",
        default=str(OUTPUT_DIR),
        help="Directory to write valparaiso_businesses.* outputs.",
    )
    parser.add_argument(
        "--user-agent",
        default=USER_AGENT,
        help="User-Agent header used for HTTP requests.",
    )
    parser.add_argument(
        "--no-reverse-geocode",
        action="store_true",
        help="Disable limited reverse-geocoding enrichment.",
    )
    parser.add_argument(
        "--max-reverse-geocode-lookups",
        type=int,
        default=MAX_REVERSE_GEOCODE_LOOKUPS,
        help="Max reverse geocode lookups performed when enrichment is enabled.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()

    # pylint: disable=global-statement
    global USER_AGENT, REFERENCE_ADDRESS, CITY_QUERY, OUTPUT_DIR
    global OUTPUT_JSON, OUTPUT_CSV, OUTPUT_MD, OUTPUT_IMPROVEMENTS_MD
    global MAX_REVERSE_GEOCODE_LOOKUPS

    USER_AGENT = args.user_agent
    REFERENCE_ADDRESS = args.reference_address
    CITY_QUERY = args.city_query
    OUTPUT_DIR = Path(args.output_dir)
    OUTPUT_JSON = OUTPUT_DIR / "valparaiso_businesses.json"
    OUTPUT_CSV = OUTPUT_DIR / "valparaiso_businesses.csv"
    OUTPUT_MD = OUTPUT_DIR / "valparaiso_businesses.md"
    OUTPUT_IMPROVEMENTS_MD = OUTPUT_DIR / "crawler_improvements_applied.md"
    MAX_REVERSE_GEOCODE_LOOKUPS = 0 if args.no_reverse_geocode else args.max_reverse_geocode_lookups

    businesses = crawl_valparaiso_businesses()
    print(f"Wrote {len(businesses)} businesses to:")
    print(f"- {OUTPUT_MD}")
    print(f"- {OUTPUT_CSV}")
    print(f"- {OUTPUT_JSON}")
    print(f"- {OUTPUT_IMPROVEMENTS_MD}")


if __name__ == "__main__":
    main()
