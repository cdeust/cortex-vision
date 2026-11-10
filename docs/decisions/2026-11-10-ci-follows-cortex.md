# The Claude verdict decides the merge, as in Cortex

Date: 2026-11-10. Owner direction, 2026-11-09: Cortex's CI is the source of truth, the
other repositories follow it, and each one gets the Claude reviews Cortex has.

## Change

- `.github/workflows/claude-review.yml` and `scripts/ci_review_budget.py` are Cortex's:
  at most three automatic reviews per pull request, each ending with `Verdict: approve`
  or `Verdict: block` (Cortex ADR-1119).
- `.github/workflows/pipeline-after-merge.yml` is new: Cortex's `resolve` and
  `close-issues` jobs with this repository's job names (contract, unit, helper, merge).
  It merges a head whose Pipeline succeeded and whose latest verdict, bound to a review
  run of that head, approves (ADR-1121). Either completion wakes it (ADR-1127).
- The `merge` job no longer arms GitHub auto-merge and holds no write permission;
  `hold.yml`, which only disarmed that auto-merge, is removed. The resolver reads the
  `do-not-merge` label and a "do not merge" title itself.
- Six test files of Cortex's resolver and budget run in `unit` (`tests/test_ci_*.py`).

## Reason

Auto-merge merged on green jobs alone: the review posted and decided nothing, had no
verdict line and no cap.

## Result

`python3 -m pytest -q tests/test_ci_*.py`: 64 passed, 18 subtests. Hosted behaviour is
proven by the first pull request after this one merges: `workflow_run` workflows run
from the default branch, so this pull request is merged by hand.
