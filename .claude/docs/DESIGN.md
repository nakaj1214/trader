# Project Design Document

> This document tracks design decisions made during conversations.
> Updated automatically by the `design-tracker` skill.

## Overview

Current fix scope includes both `/` and `/manager/confirm`.
The `/manager/confirm` fix now includes backend persistence for `remarks`
(`x_ordered` schema + update API), while keeping Blade structure unchanged.

## Architecture

<!-- System structure, components, data flow -->

```
[Component diagram or description here]
```

## Implementation Plan

### Patterns & Approaches

| Pattern | Purpose | Notes |
|---------|---------|-------|
| Frontend + minimal backend extension | Fix UI issues plus required persistence gap | Add `remarks` persistence without route redesign |
| Explicit missing-value rendering | Show missing chief/person as `"null"` | Applied in stamp fields only |
| Data-first quantity rendering | Preserve DB value in quantity input | No fallback to `1` |

### Libraries & Roles

<!-- Libraries and their responsibilities -->

| Library | Role | Version | Notes |
|---------|------|---------|-------|
| | | | |

### Key Decisions

| Decision | Rationale | Alternatives Considered | Date |
|----------|-----------|------------------------|------|
| Keep Blade templates unchanged and implement fixes in JS/CSS/PHP only | Follow scope constraint and avoid view-structure regressions | Editing `confirm.blade.php`/`order.blade.php` (rejected) | 2026-02-19 |
| Render missing chief/person as literal `"null"` in stamp cells | Align with proposal requirement | Render as blank (rejected) | 2026-02-19 |
| Use DB `ordered_number` as-is for initial quantity | Match "default to DB value" requirement | Coerce `null/0` to `1` (rejected) | 2026-02-19 |
| Expand fix plan to include `/` order total reset behavior after clear/store | Proposal includes stale total label issue outside manager screen | Keep scope manager-only (rejected) | 2026-02-19 |
| Persist manager confirm `remarks` to `x_ordered` | Proposal requires remarks input to be meaningful | Keep remarks readonly/non-persistent (rejected) | 2026-02-19 |
| Extend `update_order` API with optional `remarks` while keeping `ordered_number` required | Preserve existing quantity-update flow and add remarks persistence without route changes | Separate remarks-only endpoint (rejected) | 2026-02-19 |
| Recalculate sheet totals from active-tab subtotal cells on input/render/mode change | Keep request/list totals consistent with immediate row edits | Trust initial rendered total only (rejected) | 2026-02-19 |
| Reset `/` order total label to `¥` after store success and list clear | Eliminate stale total display when rows are cleared programmatically | Rely on input-event recalculation only (rejected) | 2026-02-19 |
| Remove project test files under `src/tests` by user policy | Align repository with "tests not used" operation policy | Keep tests for regression safety (rejected by user directive) | 2026-02-19 |
| Restrict current proposal work to GUI-only fixes (no DB/API changes) | User explicitly requested non-DB scope for this pass | Continue backend/schema changes in this pass (deferred) | 2026-02-19 |

## TODO

<!-- Features to implement -->

- [ ] 

## Open Questions

<!-- Unresolved issues, things to investigate -->

- [ ] 

## Changelog

| Date | Changes |
|------|---------|
| 2026-02-19 | Added manager confirm UI decision records (scope/null display/quantity source). |
| 2026-02-19 | Expanded scope note to include `/` order total reset requirement from proposal. |
| 2026-02-19 | Updated plan direction: add `remarks` persistence via schema/API/frontend changes. |
| 2026-02-19 | Implemented decisions: optional `remarks` on update API, active-tab total recalculation, and `/` total label reset after clear/store. |
| 2026-02-19 | Removed project test files under `src/tests` per user directive. |
| 2026-02-19 | Applied GUI-only pass: fixed single-line order `line` retrieval via hidden input value + JS fallback, and removed focus border highlight on manager confirm editable inputs. |
