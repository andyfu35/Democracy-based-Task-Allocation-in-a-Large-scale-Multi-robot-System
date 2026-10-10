# Greedy-Only Communication Robustness — Paired E2 Archives

**Status: source and regression tests committed; execution of this derived analysis on the user's Mac is pending.**

This is an **evidence-only** postprocessing study. It does not rerun any simulations, modify the Greedy optimizer, invoke Hungarian, change the 51%-majority or no-fallback 25%-plurality protocol, or introduce any additional communication assumption.

## Source data required

Both historical experiments need to be present on the same Mac checkout, with EXACTLY ONE CSV in each raw directory:

- 51% strict-majority: results/e2_joint_loss_diagonal_100r50t/raw/retirement_*.csv
- Pure >25%-announcement Greedy, **NO fallback**: results/e2_greedy_quarter_plurality_no_fallback_100r50t/raw/retirement_*.csv

Do **NOT** use results/e2_greedy_quarter_plurality_100r50t; that is the explicitly rejected self-claim fallback historical run.

Both sources must represent 100R/50T, 100 matched seeds, max_rounds=100 and Cost Loss = Vote Loss with independent packet draws. The script checks every row's method, rule, seed, dimensions, packet loss, completed task accounting and safety_failures, plus per-seed full-information Greedy reference cost identity across both sources. Historical 51%-majority raw files are allowed to omit the later-added vote_decision_rule column, but only if their method is the documented democracy_greedy_retirement.

## How to run

On the Mac, in the repository root:

    git pull
    python3 -m unittest discover -s tests -v
    python3 -m experiments.compare_greedy_communication

Default p = 0%, 10%, 20%, 30%, 40%, 50%, selected from the existing 36-level historical 0..70% sweeps. No re-simulation. Output files are written HERE, next to this README. If you already have outputs, use a **new --output-root** instead of overwriting them. The script refuses duplicate historical raw evidence because arbitrary choice of a timestamp would mix experiments.

Optional full 36-point curve (new, separate result root):

    LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"
    python3 -m experiments.compare_greedy_communication --loss-probabilities "$LEVELS" --output-root results/e2_greedy_only_communication_comparison_36point

## Generated evidence

- greedy_per_seed.csv: full original seed identity, p, rule, no-loss Greedy cost, actual complete-run cost (NaN if incomplete), individual completion, task success, Greedy executor rate, cost degradation relative to the SAME rule and seed at 0%, failed votes, simulated latency, message count, bytes and observed physical Cost/Vote attempts/drops. Expected rows: 2 × 100 × 6 = 1,200.
- greedy_rule_curve.csv: rule-and-loss means, full-task success with number of full-cost-eligible seeds, task completion, Greedy executor accuracy, completed-case-only mean cost degradation, coordination milliseconds, messages/bytes and change vs each rule's 0% control. Expected rows: 2 × 6 = 12.
- greedy_protocol_delta.csv: matched 25%-minus-51% success differences in percentage points, counts of both/only-one/neither full completion, Greedy-executor agreement difference, messages/latency/bytes differences, and cost difference ONLY for exactly matched seeds where both finished. Expected rows: 6.
- manifest.json: source SHA, SHA256 raw file hashes, selected loss axis, source locations, analysis git SHA, UTC timestamp and important limitations.

A protocol can appear artificially cheap if it leaves many tasks incomplete. **Never calculate full assignment cost gaps for incomplete runs.** A difference between two protocols is not a paired COST comparison when one finished and the other did not. The report returns NaN for cases with no comparable completed assignments rather than reporting a misleading zero or averaging only arbitrary unpaired successes.

No Hungarian column appears in any new generated CSV. Original Hungarian columns in the immutable historical files are ignored, not deleted. The benchmark still assumes reliable final-qualified-score and reliable Commit messages, so it does not prove end-to-end robustness to arbitrary wireless loss.

## Acceptance checkpoints

The source raw roots and output root must differ; all 100 seeds must match; 0% zero-loss Greedy must achieve full completion with cost and selected executors equal to the full-information Greedy; all cross-protocol per-seed reference costs must match; each input must use one distinct historical source SHA; original 51%-majority/no-fallback-25% method IDs must be correct. Any validation failure includes owner/function/category/code and will prevent new CSV export.

Detailed canonical specification and metric definitions: docs/EXPERIMENT_PROTOCOL.md Section 16. Continuity ledger: docs/CHANGE_CONTINUITY.md.
