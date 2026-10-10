# E3/E4 — 100-Robot-Capped Size and Task-Load Grid

Status: **SOURCE / TESTS COMMITTED. USER-SIDE NEW REGRESSION + FORMAL SCALING RUN PENDING.**

## What changes in the experiment

Only the number of robots and tasks. Nothing in the pure 25%-plurality Greedy algorithm changes:
- An active robot votes for its cheapest currently visible active executor.
- Strictly more than 25% of ALL active voter ballots are required for a candidate to issue a qualified final-score announcement.
- Multiple qualified announcements are compared by total received votes, lowest original robot ID breaks ties, and exactly one reliable Commit retires the executor.
- If zero candidates qualify, **no announcement and no Commit**; the task returns to the pending queue.
- No backup candidate, reliable fallback self-claim or forced task allocation is allowed.
- Same one-time Cost exchange, independently sampled remote Vote packet losses, reliable qualified-score/Commit announcements and Rady Wi-Fi latency source.

## Complete primary 30-cell matrix

| Robots | T at 10% target | T at 25% | T at 50% | T at 75% | T at 100% (1:1) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 1 | 3 | 5 | 8 | 10 |
| 20 | 2 | 5 | 10 | 15 | 20 |
| 40 | 4 | 10 | 20 | 30 | 40 |
| 60 | 6 | 15 | 30 | 45 | 60 |
| 80 | 8 | 20 | 40 | 60 | 80 |
| 100 | 10 | 25 | 50 | 75 | 100 |

Integer tasks use nearest-integer HALF UP. Actual T/R is retained because small fleets cannot represent all target load fractions exactly. Robots are capped at 100 and tasks NEVER exceed robots.

Two Cost Loss = Vote Loss conditions per size cell:
- p_cost = p_vote = 0% (control);
- p_cost = p_vote = 30% (primary impairment).

Each loss event is independently sampled at that stage. 100 paired seeds per cell/condition: **30 × 2 × 100 = 6,000 runs**.

### Fair vote-attempt allocation

The number of task-voting attempts is scaled with total tasks: **max_rounds = 2 × tasks**. In particular, 100R/50T gets 100 attempts, matching the previous study, and 100R/100T gets 200 attempts. Fixing 100 attempts across both would incorrectly make a single retry sufficient to prevent full 1:1 completion. Always compare not only full-assignment rates, but actual attempts, no-qualified attempts, communication time and cost quality.

## Commands

From the Mac repository root, after pulling:

    git pull
    python3 -m unittest discover -s tests -v

Small four-size-cell smoke (24 seed-condition runs):

    python3 -m experiments.run_e3_e4_scaling --robot-levels 10,100 --load-ratios 0.5,1.0 --loss-probabilities 0,0.30 --seeds 3 --attempts-per-task 2 --output-root results/e3_e4_scaling_smoke_100cap

Primary 30-cell formal 100-seed grid:

    python3 -m experiments.run_e3_e4_scaling --seeds 100 --output-root results/e3_e4_scaling_100robot_cap

On interrupted execution (same code SHA, grid and dataset only):

    python3 -m experiments.run_e3_e4_scaling --seeds 100 --output-root results/e3_e4_scaling_100robot_cap --resume

A completed cell is only skipped if its raw/round/event/summary evidence, seed-loss pairs, source SHA, original robot/task dimensions and exact attempt budget are all validated. A partially written cell never silently overwrites itself; preserve or manually move aside incomplete artifacts before retrying. Do not modify any source or parameter mid-experiment if resume is intended.

## Evidence layout

- benchmark_plan.json — experiment schema, SHA, task-size grid and seed/loss/attempt configuration.
- cells/R###_T###/summary.csv — per-cell original E2 per-condition metrics.
- cells/R###_T###/raw/retirement_*.csv — original raw per-seed evidence.
- cells/R###_T###/rounds/retirement_rounds_*.csv — per-task attempts, thresholds, queue transitions and Commit.
- cells/R###_T###/events/retirement_audit_*.csv.gz — designated seed-0 Cost/Vote/qualified-score/Commit events and packet delivery audit.
- summary.csv — aggregate table across all cells, one row per (R,T,p) (expected 60 rows). Generated after each validated completed cell; a partial table is NOT a formal complete result.

Aggregated metrics include full-task success, mean task Commit, Greedy CER, Hungarian CER, global cost gap ONLY for fully allocated runs, average round count, communication time/messages/bytes, actual Cost/Vote loss and number of failed no-qualified attempts. Additional task-normalized columns: mean_attempts_per_task, mean_elapsed_ms_per_requested_task, mean_messages_per_requested_task, mean_payload_bytes_per_requested_task, actual_load_ratio.

## Known limitations

This is static one-to-one allocation, not multi-task concurrency or robots taking new tasks after completing physical motion. A robot is retired after one Commit and cannot execute multiple tasks. At T=R, there are no spare robots and late tasks can have very poor global cost even if assigned. Existing source does not simulate physical movement, radio contention, burst loss, or unreliable final score/Commit announcements.

The geometry stays fixed at 100×100, therefore increased robot/task counts alter density; same seed means matching the two loss conditions WITHIN a cell, not identical geometry across different-sized cells. Experimental elapsed time is simulated communication/coordinator time, not wall-clock compute benchmark.

The earlier E2 no-fallback 89/89 test pass and 3,600-run 0–70% loss scan were on a previous commit. They do not certify this new scaling driver; new suite and formal 6,000 runs still need user-side execution. See canonical Section 15 in docs/EXPERIMENT_PROTOCOL.md and docs/CHANGE_CONTINUITY.md.
