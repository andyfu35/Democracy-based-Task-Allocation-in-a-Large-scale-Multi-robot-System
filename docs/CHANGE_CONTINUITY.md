# Change Continuity

## 2026-10-09 — Repository initialization

### Purpose
Establish the RA-L benchmark roadmap, development rules, and canonical protocol before experimental code is added.

### Files
- `README.md`
- `AGENTS.md`
- `docs/AI_CHANGE_PROTOCOL.md`
- `docs/EXPERIMENT_PROTOCOL.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions
None yet.

### Responsibility movement
None. This is a new repository.

### Preserved behavior
None; repository was empty.

### Intentionally changed behavior
None; only specifications and experiment planning were added.

### Diagnostic contract
Diagnostic categories fixed to:
`data / time / state / dependency / planning / safety / runtime / contract`.

### Open risks
- Final paper cost model is not yet frozen.
- Commit-message reliability semantics remain to be tested in E3.
- External baselines have not been implemented.

### Next step
Implement E0 Protocol Correctness Preflight.

### Commit SHA
README initialization: `37e8d5c2693bff335c4b0f4f77c63ba719544e47`.
Documentation commits: see repository history for this initialization sequence.


## 2026-10-09 — E0 Protocol Correctness Preflight implementation

### Purpose
Implement the first experiment without introducing external baselines. E0 verifies the leaderless strict-majority protocol under zero packet loss and exposes the sequential protocol's cost gap against a centralized Hungarian oracle.

### Files
- `requirements.txt`
- `democracy_mrta/__init__.py`
- `democracy_mrta/diagnostics.py`
- `democracy_mrta/scenario.py`
- `democracy_mrta/protocol.py`
- `democracy_mrta/metrics.py`
- `experiments/__init__.py`
- `experiments/run_e0.py`
- `tests/test_protocol.py`
- `results/e0_protocol_correctness/README.md`
- `results/e0_protocol_correctness/figures/.gitkeep`
- `README.md`

### Functions / owners
- `scenario.generate_e0_scenario`: deterministic synthetic E0 scenario owner.
- `scenario.compute_euclidean_cost_matrix`: E0 cost-generation owner.
- `protocol.quorum_size`: strict-majority threshold owner.
- `protocol.select_visible_candidate`: local candidate-selection owner.
- `protocol.record_vote`: vote validation/deduplication owner.
- `protocol.resolve_unique_majority`: quorum resolution and multiple-winner safety boundary.
- `protocol.run_zero_loss_task_round`: one zero-loss task-round execution owner.
- `protocol.run_zero_loss_allocation_epoch`: sequential one-to-one epoch owner.
- `metrics.hungarian_oracle_cost`: centralized oracle owner.
- `metrics.evaluate_e0`: E0 metric owner.
- `experiments.run_e0.run_one_seed`: one paired E0 seed owner.
- `experiments.run_e0.build_summary`: E0 aggregation owner.

### Responsibility movement
None; these are the first code owners in the new repository.

### Preserved behavior
The canonical protocol remains task-order sequential, leaderless, and strict-majority based. Task dissemination remains reliable in the primary model.

### Intentionally changed behavior
Executable E0 behavior now exists. The E0 synthetic cost is Euclidean distance only and is explicitly not the final paper cost model.

### Diagnostic contract
Protocol failures use structured `Diagnostic` values with owner / function / category / code / expected / actual / details. Safety-relevant boundaries include duplicate execution and multiple quorum winners. Vote validation explicitly rejects stale and duplicate votes.

### Verification status
Code and unit tests are committed. A clean remote execution attempt could not run because the execution container cannot resolve github.com; therefore this entry does **not** claim a passing local/formal run. The formal result remains pending the user's local execution.

### Open risks
- Sequential task ordering can produce non-zero global optimality gap versus Hungarian even at 0% loss.
- Final paper cost model remains unfrozen.
- Packet-loss transport is intentionally deferred until E2/E3.
- Commit-loss semantics remain deferred until E3.

### Next step
Run E0 locally with 100 seeds, preserve raw and summary CSVs, then update the README result ledger before starting E1.

### Commit SHA
Implementation sequence is represented by:
- protocol: `5ec7796c80ac94289e19077ea605e22711ee20db`
- metrics: `5c8059c0fcba49f537a87e80a74f2e730e0fbf8b`
- runner: `959f03a723b5fc9b03f3a7b928197be3ada65853`
- tests: `441232a96529f6b2cc40fc74d9cf8e795080a270`
- repository state through result-directory setup: `7082518a798c840e6c76d785035379864dd1f97b`
- README run-instruction update: `57af1134d9c59e6889898199546b0fbd1f2c2cb9`


## 2026-10-09 — E0 local formal result record

### Purpose
Record the first 100-seed-per-condition local E0 execution without changing protocol behavior.

### Files
- `README.md`

### Functions
No code functions changed.

### Responsibility movement
None.

### Preserved behavior
The canonical sequential per-task voting protocol remains unchanged.

### Intentionally changed behavior
None. This change records experimental evidence only.

### Verification result
- Unit tests: 5/5 passed.
- Conditions: 10R/5T, 25R/10T, 50R/30T, 100R/50T, 100R/100T.
- Seeds: 100 per condition; 500 scenarios total.
- ASR: 1.0 for every condition.
- Safety failures: 0.
- Replay failures: 0.
- Mean optimality gaps: 4.097006%, 5.062453%, 11.313390%, 8.626984%, 35.119499% respectively.
- Largest observed condition-level mean gap: 35.119499% at 100R/100T.

### Diagnostic contract
No diagnostic failures were emitted in the local run.

### Open risks
The 35.12% zero-loss mean gap at 100R/100T shows that sequential task-order assignment can materially sacrifice global assignment quality under saturated load. This must be resolved as a paper-design decision before claiming near-optimality. The local raw file `results/e0_protocol_correctness/raw/e0_20261009T130507Z.csv` and generated `summary.csv` have not yet been confirmed committed to GitHub.

### Next step
Commit the local E0 raw/summary files. Then make an explicit architecture decision: preserve sequential per-task voting and present its quality/robustness trade-off, or revise the proposal stage to optimize the multi-task assignment before proceeding to E1 external baselines.

### Commit SHA
README result update: `d89c8006c0bf408616bb5f0f8bf4677977a17101`.
