# Review quotation expiry warnings (#27, first slice)

Review shows quotations whose latest published version expires between its Shanghai reference date and that date plus 14 calendar days, both inclusive. The reference date is the selected completed period's last day, or today for the current period. Versions published after the cutoff are excluded.

This is an actionable list with **current** processing state, not a reconstruction of historical quotation status. This rule was confirmed by the product owner. Accepted, rejected, superseded, expired, and closed-opportunity quotations are excluded; a date already past today is also excluded even if the expiry job has not run. Creating a new draft does not hide the still-valid published version. Replacing the published version moves the warning to the replacement's expiry date.

Counts are unique quotation records. Details show their current quotation owner, customer, exact formal version, expiry date, and days relative to the reference date, nearest expiry first. Links open that version even if a newer draft exists. Customer master region/market and current quotation owner determine scope; existing Manager-only Review permissions apply. Missing formal-version data makes the count unavailable rather than zero; known rows remain inspectable.

If the opportunity changes customer after publication, quotation scope still follows the quotation customer snapshot. Its linked opportunity's current stage is checked separately, including outside the selected customer filter, so closed deals do not reappear in a narrower scope. This lookup reads only ID/stage and does not expand any other Review metric or detail list.

Optional site setting `crm_cockpit_quote_expiry_days` accepts an integer from 0 to 365; invalid values fall back to 14. No schema or data migration is required.

Validation covers inclusive day 0 / day 14 boundaries, current-day expiry, Shanghai timestamps, draft/replacement and terminal states, malformed data, ownership/scope, real quotation publishing and decisions, Manager authorization, configurable horizon, detail pagination, and version-link loading/retry.

This implements only the quotation-expiry slice of #27. Other risk types, custom dismissal/action records, and notifications are separate work; this PR does not close the whole issue.
