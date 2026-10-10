# E2 Greedy Vote Loss sensitivity — benchmark evidence ledger

Status: **RUNNER EXTENSION COMMITTED; NEW UNIT TESTS AND FORMAL RUNS PENDING USER-SIDE EXECUTION**.

The existing Cost-only curve with 100 robots / 50 tasks / 100 seeds had a 99% all-task success rate at p_cost_loss=0.30, p_vote_loss=0. This is **not** evidence for the new Vote Loss or joint-loss conditions.

## Fixed protocol / method

- Method: democracy_greedy_retirement (one pending task at a time).
- Each active robot selects cheapest currently visible active robot from its independently incomplete local cost view; each robot always keeps own row.
- Initial complete task cost row is broadcast only once. Missing cost rows remain unavailable in later voting attempts.
- Vote messages to remote candidates undergo separately sampled Bernoulli Vote Loss; self-votes are local, never exposed to the Vote Loss channel.
- Per-task strict majority uses active voter count; reliable commits are followed by executor retirement. No-quorum moves the attempted task to the end of pending queue.
- 100 robots, 50 tasks, 100 paired seeds, 100 task-voting attempts maximum. All physical execution and lost commit announcements are outside scope.

## Four evidence families

| Experiment | Cost Loss | Vote Loss | Seeds | Output root |
| --- | --- | --- | --- | --- |
| Historical cost-only (already measured) | 0–70% by 2% | 0 | 100 per condition | results/e2_greedy_retirement_100r50t |
| Vote-only (new) | 0 | 0–70% by 2% | 100 | results/e2_vote_only_100r50t |
| Fixed cost 30% + Vote sweep (new) | 0.30 | 0–70% by 2% | 100 | results/e2_cost30_vote_sweep_100r50t |
| Joint diagonal (new) | 0–70% by 2% | equal numeric probability to Cost Loss | 100 | results/e2_joint_loss_diagonal_100r50t |

The last three families are 3 × 36 × 100 = 10,800 new seed-condition simulations.

Optional interaction surface: an 8 × 8 Cartesian product over 0–70% by 10% in each dimension, with 100 seeds per cell (6,400 seed-condition simulations), stored at results/e2_joint_loss_grid_100r50t.

## Commands

After `git pull`, run the full test suite, then:

```bash
# 3-seed smoke: 2 cost levels x 3 vote levels = 6 conditions
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.30 --vote-loss-probabilities 0,0.30,0.70 --max-rounds 100 --output-root results/e2_vote_loss_smoke

LEVELS="$(python3 -c 'print(",".join(f"{i/100:.2f}" for i in range(0, 71, 2)))')"

python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities 0 --vote-loss-probabilities "$LEVELS" --max-rounds 100 --output-root results/e2_vote_only_100r50t

python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities 0.30 --vote-loss-probabilities "$LEVELS" --max-rounds 100 --output-root results/e2_cost30_vote_sweep_100r50t

python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --cost-loss-probabilities "$LEVELS" --loss-pairing diagonal --max-rounds 100 --output-root results/e2_joint_loss_diagonal_100r50t
```

## Acceptance criteria

- All tests including `tests/test_vote_loss_sweep.py` pass.
- Smoke prints 6 conditions and 18 total seed-condition simulations.
- Each formal 1D curve prints 36 conditions and 3,600 total seed-condition simulations.
- At p_cost=p_vote=0, all 50 tasks commit and Greedy-reference correct executor rate is 1.
- Observed Vote Loss is calculated from dropped/attempted **remote vote packets**, not from self-votes; Cost Loss is calculated separately from initial peer cost deliveries.
- First failing packet phase is not inferred from task commitment alone; audit fields must reconcile exactly with simulator delivery observations.
- Final assignments have no reused robot and no repeated task; all reported safety failures remain zero.
- Cost gap is calculated only for fully completed 50-task allocations; incomplete conditions report NaN, not zero.
- All code commits, raw per-seed CSV, per-round CSV, designated audit log and summary CSV are preserved under distinct output roots.
- Any apparent robustness improvement based on more retries must be compared at matched max_rounds and reported with rounds, messages and latency.

Primary plot: Vote Loss percentage on x axis; Task Commit, all-task Full Success, and Greedy-reference Correct Executor Rate on y axis. Supporting plots: average attempts/coordination time; actual remote Vote Drop rate; Cost-only vs Vote-only vs Cost30+Vote vs Joint Diagonal, with clear axis definitions.

The new formal results are **not yet available** in this repository. Do not substitute values predicted from binomial assumptions as measured outcomes.
