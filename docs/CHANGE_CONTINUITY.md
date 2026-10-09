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


## 2026-10-09 — Experiment architecture redefinition: fixed optimizer + empirical network timing

### Purpose
Refocus the paper on the communication/agreement contribution. Remove optimizer-comparison as the primary experimental question, fix Hungarian as the common optimizer, and define an externally grounded wireless-latency model.

### Files
- `README.md`
- `docs/EXPERIMENT_PROTOCOL.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions
No code functions changed in this documentation-only change.

### Responsibility movement
- Optimization responsibility is frozen as a shared deterministic Hungarian backend.
- Experimental differentiation moves to the communication/agreement layer.
- Network timing becomes an explicit future owner; per-message timing must be event-driven.

### Preserved behavior
- Leaderless strict-majority voting remains the core Democracy protocol.
- Reliable initial task/epoch dissemination remains the primary assumption.
- Packet-loss resilience remains the principal robustness claim.

### Intentionally changed behavior
- Primary experiments no longer compare Greedy/MILP/Hungarian as competing optimizers.
- Hungarian is now fixed across controlled coordination methods.
- The previous sequential per-task E0 implementation/results are classified as obsolete/invalid for the new canonical definition and retained only as historical evidence.
- The formal experiment sequence is now E0-E7 and includes explicit empirical wireless latency and real-trace replay.

### Network timing evidence
Primary empirical reference:
M. Rady et al., “How does Wi-Fi 6 fare? An industrial outdoor robotic scenario,” Ad Hoc Networks 156, 103418, 2024, DOI 10.1016/j.adhoc.2024.103418.

The authors' public repository `minarady1/wifi_for_industrial_robotics` provides processed application-level ROS 2 fields including `control_delay_ms` and `control_loss`. Controlled timing experiments will bootstrap per-message delay from a pinned Wi-Fi 6 trace/profile instead of assuming a single constant latency.

### Diagnostic contract
No code diagnostic changes. Future timing implementation must use explicit network/time boundaries and must not silently fill missing optimizer inputs from ground truth.

### Open risks
- The exact Wi-Fi 6 location/PHY trace to serve as the primary profile must be pinned during E1 implementation.
- Missing-cost feasibility semantics for partial local Hungarian matrices require explicit implementation and tests before E2.
- A shared-medium contention model beyond empirical per-message delay may be needed for very large fleets; this must not be invented silently.
- Current code still implements the obsolete sequential E0 and must be replaced before new formal results are generated.

### Next step
Reimplement E0 under the new canonical full-matrix Hungarian proposal protocol. Require zero optimality gap at complete information. Then implement the network timing owner using the pinned Rady et al. empirical trace for E1.

### Commit SHA
README: `83e4961d4508aaf881f1c847ac5e76068594997a`
Canonical protocol: `95d36911d43b4786ff9b81d1062c9162caa31950`
