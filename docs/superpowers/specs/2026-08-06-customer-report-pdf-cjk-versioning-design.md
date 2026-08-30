# Customer Report PDF CJK and Versioning Design

## Problem

The released Customer Report is server-generated. Its Arial-only template runs in an image without a CJK font, so Chinese content renders as empty boxes. It also exposes the owner login and cannot issue a corrected immutable version.

## Approved Direction

- Keep backend rendering authoritative and ignore client PDF bytes.
- Install Noto CJK and use it in reports and controlled watermarks.
- Render a structured customer-facing A4 report from canonical data.
- Show the Frappe User full name, with login as fallback.
- Preserve v1 and append v2 for corrected releases in Customer Review.
- Keep stored Test Run values, including Lot `5`, unchanged.

## Acceptance Criteria

1. Chinese customer, title, summary and user name are readable and extractable.
2. Context, performance, conclusion/readiness and integrity sections are visible.
3. Owner uses the display name when available.
4. A repeated release creates v2 without deleting or changing v1.
5. Permission, readiness, rollback and controlled-download protections remain active.
