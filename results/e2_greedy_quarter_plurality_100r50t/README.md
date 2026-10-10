# ARCHIVED — Rejected 25% plurality with self-claim fallback (historical experiment)

**Status: USER-RUN EXPERIMENT COMPLETED ON 2026-10-10; DECISION RULE REJECTED BY THE USER AND REMOVED FROM CURRENT RUNTIME.**

This directory's original experiment used the now-removed quarter_plurality_fallback rule. It added reliable broadcasts from every active robot when nobody received more than 25% of the vote, then forced a unique commit via the extra reliable self-claim channel. It was not the intended pure 25% plurality design.

Historical provenance from the user-provided Mac terminal log:
- Git HEAD: 6cf14239ffd427c45b1f5311749fa7034c02bc59.
- 85/85 unit tests passed for that historical implementation.
- 100 Robots, 50 Tasks, 100 seeds, 36 diagonal loss conditions, p_cost_loss=p_vote_loss between 0% and 70% in 2% steps: 3,600 seed-condition runs completed.
- The historical experiment reported 100% all-task assignment for 0–70% loss.
- At 70% Cost/Vote loss, the **fallback was used for approximately 99.98% of tasks**. These results cannot establish genuine pure 25% plurality performance or tolerance of real control-channel loss.
- Reported under the original runner at results/e2_greedy_quarter_plurality_100r50t/summary.csv. Actual raw/round/event CSV results remain on the user's Mac and were not committed in this repository.

## Important correction

The user explicitly rejected the fallback logic as not part of their algorithm. The current source intentionally rejects the obsolete quarter_plurality_fallback API rule with diagnostic REMOVED_PLURALITY_FALLBACK_RULE. Old run instructions using this option no longer work by design; do not silently reinterpret old results.

The new no-fallback experiment:
- decision rule: quarter_plurality;
- no candidate >25%: **no winner, no announcement, no commit; rotate task and retry**;
- result root: results/e2_greedy_quarter_plurality_no_fallback_100r50t;
- canonical source: docs/EXPERIMENT_PROTOCOL.md Section 14.

Preserve old raw evidence on the Mac if available. Do not delete or overwrite it, and do not combine this archived fallback curve with the new no-fallback method in a single undifferentiated metric.
