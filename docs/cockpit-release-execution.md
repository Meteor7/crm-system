# Cockpit release execution

This ledger tracks the release work authorized on 2026-09-28. A row is complete only when its candidate, tests and reviews are recorded. Existing implementation is being integrated, not reimplemented.

## Delivery and review contract

- Work in the attached worktree on `codex/cockpit-release-main`, based on main `d09abac9f00f72e44e824512640626e04165b364` and cockpit `5660a9e67a033f4b5577dd4379b9b242ef901727`.
- Preserve both sides of the #35/#54/#79/#84 and cockpit fixes. Review the final integrated tree against main, not just the merge resolutions.
- Before pushing each candidate, request **对抗性审查pr**: an independent broad review by GPT-5.6-sol xhigh and Claude Code Opus 5.5 xhigh. Assess each finding before editing; repeat after fixes until both approve the candidate.
- After pushing, request `@codex review`, inspect its response and CI against the pushed commit, address valid findings, and repeat the local dual review and remote review for changed candidates.
- Prefer the shortest usable release path. Deferred features must remain explicit in their existing issue or a new issue; deferral is not an implementation claim.
- No production deployment or PR merge has been performed by this execution.

## Integration decisions

- #36 is an intentional feature change: new Opportunities need a probability level; a set level cannot be cleared; a downgrade needs a reason and plan. Preserve #35's separate account/type guards, current Booking prefill and concurrency rules.
- Main's Visit Meeting Record permission and cockpit's Action/History/Recovery/Loss Review/Status permissions must coexist. Read-scope registration is not permission to cascade-delete a record.
- Status alone has the 140-character filename boundary from #54; the shared upload validator is unchanged.
- Existing confirmed orders cannot switch currency through ordinary edits and thereby clear the recorded CNY amount. Pending drafts remain editable. Manager corrections retain their dedicated reasoned path.
- Newly integrated Booking correction endpoints follow #84's Opportunity-before-Booking lock order and update the source Opportunity version.

## Work inventory

| Work | Issue | Current disposition |
|---|---|---|
| Existing cockpit integration and confirmed-order correction | #83 stack, #35/#54/#79/#84 | Implementing locally; not yet reviewed or pushed |
| Child-record scope | #67 | Release foundation; pending |
| Contact File revocation and managed upload ingress | #56/#78 | Release foundation; pending |
| Notification source scope, unreachable recipients, plan-change notification | #57/#75/#51 | Release foundation; pending |
| RFQ pagination and query amplification | #58/#82 | Before bulk historical loading; implementation/defer decision pending |
| Permission registration/drift gate | #68/#82 | Minimum regression protection; full framework deferred in existing #68 |
| Cross-version browser recovery | #11/#60 | Release foundation; pending |
| S1 unknown amount, Demo exit, activity business dates | #22/#73/#72/#26 | Determine first-trial need; remain tracked, not delivered |
| Territory, targets, shared scope and period | #17/#20/#18 | Subsequent feature batch; remain tracked, not delivered |
| Controlled historical entry | #14 | Requires concrete data list and business-date contract; not delivered |
| Review, Warnings and Plan remaining requirements | #20/#25/#27/#28 | Compare integrated behavior before selecting release blockers |
| Query expression and sharing/export | #21 | Separate review boundaries; remain tracked, not delivered |
| Document entry and Blue Sheet fields/integration | #29 | Remain tracked; existing Win Result must not be rebuilt |
| Internal AI, external evidence, scheduled sharing | #30/#31/#32 | Later feature phases after factual data and access boundaries |
| Equipment unavailability warning | #27 | Needs an authoritative resource source and maintainer |

## Release evidence still required

- Integrated frontend typecheck, tests and production package verification.
- Full backend tests on a dedicated Frappe 15 / MariaDB 10.6 stack, plus relevant real HTTP role/negative cases.
- Independent local dual-review reports pinned to the same candidate.
- Pushed PR, GitHub CI and `@codex review` resolution for that candidate.
- Before deployment: #74 final-candidate migration rehearsal on a fresh backup, #80 Sales probability confirmation, #81 exact legacy-stage preflight, #50/#60 recoverable database/files/configuration and same-artifact promotion.
- History coverage must be set from proven rollout/migration dates; missing history is not zero and is never invented. Scheduler/worker health already matters to the existing daily jobs.

## Tool verification

The installed global Claude Code 2.1.204 rejected Opus 5.5. A task-local Claude Code 2.1.283 was installed under the private task directory; a probe using `--model claude-opus-5-5 --effort xhigh` succeeded and reported that exact model. This is tool availability evidence, not a code-review approval.
