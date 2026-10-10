# Sequential Greedy Democracy with executor retirement (100R/50T)

Status: **IMPLEMENTED; LOCAL VERIFICATION AND 100-SEED RUN PENDING**.

Algorithm (not Hungarian):
1. All 100 robots share their full 50-task cost row ONCE. Each other robot independently receives or loses the full row according to Cost Loss p_c. A robot always retains its own row.
2. For the head pending task, each currently unassigned robot votes to the **lowest-cost visible active executor**. Deterministic tie-break: original robot ID.
3. Only a receiver with more than half of the active robots' valid ballots can announce a reliable commit.
4. The committed executor/task are excluded from every later vote, and the next task becomes head. Quorum is recomputed each round from the remaining active robots.
5. On quorum failure the attempted task moves to queue tail without retiring anyone; new vote transport trials use the next round ID. The initial cost rows are NOT refreshed.
6. Stop at max_rounds attempts; report partial completion explicitly.

Default experiment:
- 100 robots, 50 tasks; 100 scenario/network seeds.
- Cost Loss: 0% to 70%, 2 percentage-point increments (36 points).
- Vote Loss 0% (cost-only ablation).
- Maximum 100 task-vote attempts. At zero loss exactly 50 attempts are necessary to commit 50 tasks.
- Original E2 is not modified.

```bash
git pull
python3 -m unittest discover -s tests -v

# Smoke
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 3 --cost-loss-probabilities 0,0.3,0.5 --vote-loss-probability 0 --max-rounds 100 --output-root results/e2_greedy_retirement_smoke

# Full experiment
python3 -m experiments.run_e2_retirement --robots 100 --tasks 50 --seeds 100 --vote-loss-probability 0 --max-rounds 100 --output-root results/e2_greedy_retirement_100r50t
```

Output:
- `raw/retirement_<timestamp>.csv`: all seed/loss results, timestamp, Git HEAD, final assignments, coverage, Greedy/Hungarian reference metrics, total communication rounds/bytes.
- `rounds/retirement_rounds_<timestamp>.csv`: per-round task attempted, complete pending queue, eligible physical IDs, strict-majority threshold, winner, duration, delivery counts.
- `events/retirement_audit_<timestamp>.csv.gz`: seed-0 cost deliveries and subsequent vote/commit messages with physical sender/receiver IDs and epoch ID.
- `summary.csv`: first-task success, eventual commit, Greedy oracle CER, original full-Hungarian oracle CER, complete-assignment total-cost gap to both oracles, rounds and time.

Interpretation:
- At 0% loss the final assignment should match **full-information SEQUENTIAL GREEDY**, not necessarily global Hungarian optimum.
- Hungarian is computed solely for an external evaluation benchmark, not for voter proposal planning.
- If a run leaves tasks unassigned, its completed-pair cost cannot be used as a full-assignment cost-gap measurement; those gap fields are NaN.
- A retry of the exact same task with identical active membership and zero Vote Loss will not improve information completeness, since cost rows are not refreshed.
- The simulator does not model physical task travel/execution, robots returning to service, packet-loss of commit announcements, or real Wi-Fi channel contention.

Until tests and smoke pass locally, do not cite these as completed performance results.
