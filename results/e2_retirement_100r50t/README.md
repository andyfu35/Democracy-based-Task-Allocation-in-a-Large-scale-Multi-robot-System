# E2 retiring-executor / dynamic-electorate experiment

Status: IMPLEMENTED, **LOCAL TEST AND FORMAL RUN PENDING**.

This is an additional opt-in multi-round experiment. It is not a replacement for the single-round E2 controls or their previously observed success curves.

## Process

Every eligible robot computes Hungarian using its own independently lossy local cost rows for the *currently active* robot/task subset, then unicasts task votes. Per-task quorum is a strict majority of the frozen electorate for **that round**.

After an executor reaches quorum, it broadcasts a reliable commit for its task. The robot exits the voter/candidate set **starting the next round**, and its committed task leaves the pending pool. Re-run cost exchange and Hungarian on the reduced problem. No-quorum tasks remain pending. A configured maximum number of rounds ends retries if completion cannot be reached.

`p_cost_loss` and `p_vote_loss` are separate; default E2 retirement experiment uses vote loss 0, cost loss sweeping 0-70% by 2 points.

Important: this is a static allocation model. An assigned robot enters an unavailable / committed state for the remainder of this allocation run; physical task travel/execution and later rejoining are not simulated.

## Local commands

```bash
git pull
python3 -m unittest discover -s tests -v
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.3,0.5 --vote-loss-probability 0 --max-rounds 5 --output-root results/e2_retirement_smoke
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --vote-loss-probability 0 --max-rounds 10 --output-root results/e2_retirement_100r50t
```

## Output

- `raw/retirement_<timestamp>.csv`: full per-seed, per-loss paired experimental rows, provenance with Git HEAD.
- `rounds/retirement_rounds_<timestamp>.csv`: active robot IDs, remaining task IDs, strict-majority quorum, committed pairs, communication counters, round times.
- `events/retirement_audit_<timestamp>.csv.gz`: seed 0's per-message/per-delivery audit, with epoch ID and original physical sender/receiver/task IDs.
- `summary.csv`: first-round versus bounded multi-round task commit/CER, full success, global optimum probability, mean rounds, communication time and message cost.

Only compare total-cost optimality gap against the original full-information Hungarian oracle when **every task** committed. CER uses each task's original oracle-assigned executor, and may penalize different equal-cost alternatives.

No new E2 one-round results have been modified.

## Unresolved

- A reliable commit is assumed; if any peer misses a commit, membership can diverge and requires a separate safety/recovery protocol.
- No actual execution latency, physical robot motion, repeat-task availability or MAC contention.
- Reducing the voting population can sometimes **decrease**, not always increase, quorum success.
- Multi-round attempts can improve eventual completion by new packet deliveries and re-optimization but cost additional time/traffic; no guaranteed convergence or global optimality.
- The 100-seed experiment and new tests have not been executed by the assistant.
