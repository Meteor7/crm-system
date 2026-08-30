# Quotation QTY Integer Design

Date: 2026-08-10

## Goal

Quotation device and accessory quantities must be positive whole numbers. Users must not be able to save fractional quantities, and the system must never silently round a value.

## Scope

- Apply the same rule to Device and Accessory quotation lines.
- The editor uses a numeric input with `min=1` and `step=1`.
- Draft save and formal publish share server-side validation requiring an integer greater than zero.
- Existing pricing, tax, discount, versioning, PDF, and historical quotation behavior remains unchanged.
- Existing records are not migrated automatically.

## Data flow and errors

The browser sends the entered quantity unchanged. The quotation service validates it before calculating line totals or writing child rows. Empty, zero, negative, and fractional quantities return the existing `VALIDATION_ERROR` response. The UI displays the existing save error state and retains the last successfully saved preview.

## Testing

- Rule test: integer quantities calculate normally.
- Rule test: device and accessory fractional quantities are rejected.
- API/integration test: a fractional quantity cannot be saved.
- UI test: both quantity inputs expose `min=1` and `step=1`.
- Build, focused tests, Docker deployment, and LAN browser verification are required before completion.