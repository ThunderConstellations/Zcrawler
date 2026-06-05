## 2025-05-22 - Replacing Alerts with Inline Feedback
**Learning:** Browser `alert()` is highly disruptive and feels "unpolished" in a modern AI-powered dashboard. Inline feedback on the triggering button (changing text/color) provides a smoother, non-blocking experience that keeps the user in their context.
**Action:** Always prefer inline status indicators (spinners, checkmarks, text changes) over native modal dialogs for common state updates.

## 2025-05-22 - Accessibility in Dynamic Tables
**Learning:** When using JavaScript to render table rows, developers often forget `aria-label` for action buttons (like Delete). Screen reader users only hear "button" without these labels.
**Action:** Ensure that all dynamically generated buttons include descriptive ARIA labels and focus states.

## 2025-05-22 - Dashboard Consistency & Information Density
**Learning:** Large dashboards benefit from clear hierarchical separation. Using lowercase/uppercase pairings with icons for headers creates a professional, "industrial" feel (like the reference image). Standardizing these patterns across all sections (Definitions, Runs, Settings) reduces cognitive load.
**Action:** Establish a "Header Pattern" (Icon + Uppercase tracking-wider text) and apply it globally to all main sections.

## 2025-05-22 - Searchable Lists for Scalability
**Learning:** Even if a list is small now, providing a filter/search bar (especially for "Definitions" or "Workflows") signals that the app is built for scale. Real-time JS-based filtering is a low-cost, high-impact UX win.
**Action:** Always include a search bar for primary entity lists (Crawlers, Runs, Findings).
