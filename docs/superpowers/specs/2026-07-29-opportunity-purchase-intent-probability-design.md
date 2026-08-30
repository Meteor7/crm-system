# Opportunity Purchase Intent Probability Design

## Goal

Extract the deterministic probability formula from `semiconductor-crm-demo.html` and reuse it in the CRM Opportunities module.

## Source Algorithm

The prototype defines these stage base probabilities:

| Stage | Base probability |
|---|---:|
| 需求发现 | 15 |
| 技术确认 | 30 |
| Demo验证 / Demo 验证 | 55 |
| 预算审批 | 70 |
| 报价 / 商务谈判 | 80 |
| 采购流程 | 90 |
| Won | 100 |
| Lost | 0 |

For an open opportunity:

`probability = round(stageBase × 0.6 + purchaseIntent × 0.4)`

The result is clamped to `0..100`. `Won` always returns `100`; `Lost` always returns `0`.

## Scope

- Keep `StrategyOpportunityDto.score` as the persisted purchase-intent value for backward compatibility.
- Add `intentScore` to Opportunity create/update input and remove manual probability entry from the UI.
- Calculate probability in one pure domain function.
- Recalculate existing Mock opportunities when the API session starts.
- Recalculate after create, edit, or stage advancement.
- Show purchase intent and calculated probability in the Opportunities list, detail, and editor preview.
- Do not modify Leads, Booking, permissions, Frappe backend schemas, or unrelated modules.

## Data Flow

1. The user selects an Opportunity stage and enters purchase intent from `0` to `100`.
2. The editor previews the calculated probability.
3. The Mock API validates purchase intent and calculates probability from the shared domain function.
4. The stored Opportunity keeps `score` as purchase intent and `probability` as the calculated result.
5. All Opportunity consumers receive the same calculated value.

## Compatibility

- Existing stored records reuse their current `score` as purchase intent.
- `Demo 验证` maps to the prototype's `Demo验证`.
- `商务谈判` maps to the prototype's `报价` base probability.
- Existing callers that still send `probability` are accepted temporarily as a fallback purchase-intent input, while the Opportunities UI sends `intentScore`.

## Validation

- Amount must be non-negative.
- Purchase intent must be a finite number between `0` and `100`.
- Unknown stages use a base probability of `0`, matching the prototype fallback.

## Acceptance Criteria

- The extracted pure function returns the prototype's hand-calculated values.
- OPP-003 (`采购流程`, purchase intent `86`) displays probability `88%`.
- Changing only the stage recalculates probability.
- Changing only purchase intent recalculates probability.
- Won and Lost remain fixed at `100%` and `0%`.
- Opportunity forms display purchase intent as the editable input and probability as read-only calculated output.
- Focused tests, typecheck, build, and rendered browser checks pass.
