## 2025-05-22 - Replacing Alerts with Inline Feedback
**Learning:** Browser `alert()` is highly disruptive and feels "unpolished" in a modern AI-powered dashboard. Inline feedback on the triggering button (changing text/color) provides a smoother, non-blocking experience that keeps the user in their context.
**Action:** Always prefer inline status indicators (spinners, checkmarks, text changes) over native modal dialogs for common state updates.

## 2025-05-22 - Accessibility in Dynamic Tables
**Learning:** When using JavaScript to render table rows, developers often forget `aria-label` for action buttons (like Delete). Screen reader users only hear "button" without these labels.
**Action:** Ensure that all dynamically generated buttons include descriptive ARIA labels and focus states.
