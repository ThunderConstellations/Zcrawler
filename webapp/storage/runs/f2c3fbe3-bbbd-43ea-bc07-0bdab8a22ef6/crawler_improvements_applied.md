# Crawler Improvements Applied

- Switched to business-focused Overpass filters for better signal quality.
- Added contact enrichment fields: `email` and `opening_hours` when available.
- Normalized phone and website values for cleaner output.
- Added quality scoring so richer records rank higher within similar distances.
- Added limited reverse-geocode enrichment for nearest records missing street addresses.
- Preserved source IDs (`type:id`) for traceability and debugging.
