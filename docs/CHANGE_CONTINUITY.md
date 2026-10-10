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


## 2026-10-09 — Corrected E0 full-matrix Hungarian proposal voting

### Purpose
Replace the obsolete sequential per-task minimum-cost E0 implementation with the canonical paper algorithm: each robot runs the same full-matrix Hungarian optimizer, converts the resulting assignment into task-level votes, and commits each task through strict-majority quorum.

### Files
- `democracy_mrta/optimizer.py`
- `democracy_mrta/protocol.py`
- `democracy_mrta/metrics.py`
- `democracy_mrta/__init__.py`
- `experiments/run_e0.py`
- `tests/test_optimizer.py`
- `tests/test_protocol.py`
- `tests/test_metrics.py`
- `results/e0_protocol_correctness/README.md`
- `README.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions / owners
- `optimizer.validate_cost_matrix`: owns optimizer input validation.
- `optimizer.solve_hungarian_assignment`: owns the fixed exact assignment optimizer.
- `protocol.assignment_to_votes`: owns conversion from one local assignment proposal to task-level votes.
- `protocol.record_vote`: preserves vote validation and deduplication.
- `protocol.resolve_unique_majority`: preserves the quorum safety boundary.
- `protocol.compute_zero_loss_local_proposals`: owns the E0 requirement that all complete-information local proposals are identical.
- `protocol.collect_zero_loss_vote_ledgers`: owns zero-loss vote collection.
- `protocol.resolve_zero_loss_epoch`: owns unanimous per-task commit and one-to-one safety checks.
- `protocol.run_zero_loss_allocation_epoch`: orchestrates corrected E0 only.
- `metrics.require_zero_loss_optimality`: owns the hard zero-gap contract.
- `metrics.evaluate_e0`: evaluates corrected E0 against the same Hungarian oracle.
- `experiments.run_e0.run_one_seed`: records oracle-assignment mismatch and non-unanimous task diagnostics in addition to prior E0 metrics.

### Responsibility movement
Hungarian optimization moved out of protocol/metrics into the dedicated `optimizer` owner. The protocol no longer selects a per-task minimum-cost robot or removes a winner before solving subsequent tasks. Protocol responsibility is now proposal-to-vote-to-quorum only.

### Preserved behavior
- strict-majority quorum;
- duplicate-vote rejection;
- stale-round rejection;
- one-to-one static assignment model;
- deterministic seed replay;
- E0 synthetic Euclidean cost generation.

### Intentionally changed behavior
- Removed obsolete sequential task-wise greedy behavior.
- Removed the behavior equivalent to `eligible.remove(winner)` before solving later tasks.
- Each voter now solves the full cost matrix with Hungarian before casting task-level votes.
- Zero-loss E0 now requires unanimous votes and exact equality with the Hungarian optimum.
- Any nonzero zero-loss cost gap now fails at `metrics.require_zero_loss_optimality` with category `contract` and code `ZERO_LOSS_OPTIMALITY_MISMATCH`.

### Diagnostic contract
New important diagnostics:
- `optimizer.validate_cost_matrix / data / EMPTY_COST_MATRIX`
- `optimizer.validate_cost_matrix / data / EMPTY_TASK_SET`
- `optimizer.validate_cost_matrix / data / NON_RECTANGULAR_COST_MATRIX`
- `optimizer.validate_cost_matrix / contract / TASKS_EXCEED_ROBOTS`
- `optimizer.validate_cost_matrix / data / NONFINITE_COST`
- `optimizer.solve_hungarian_assignment / contract / INCOMPLETE_HUNGARIAN_ASSIGNMENT`
- `protocol.compute_zero_loss_local_proposals / contract / ZERO_LOSS_PROPOSAL_MISMATCH`
- `protocol.collect_zero_loss_vote_ledgers / contract / PROPOSAL_COUNT_MISMATCH`
- `protocol.collect_zero_loss_vote_ledgers / contract / UNEXPECTED_ZERO_LOSS_VOTE_REJECTION`
- `protocol.resolve_zero_loss_epoch / contract / ZERO_LOSS_VOTE_NOT_UNANIMOUS`
- `protocol.resolve_zero_loss_epoch / safety / DUPLICATE_EXECUTION`
- `metrics.require_zero_loss_optimality / contract / ZERO_LOSS_OPTIMALITY_MISMATCH`

### Verification status
The corrected implementation and tests are committed, but this environment has not executed the repository test suite. Formal verification is intentionally pending the user's local run.

### Open risks
- Deterministic tie behavior currently relies on identical matrix ordering and the same SciPy Hungarian implementation on every robot. A cross-runtime tie-policy test may be needed before distributed physical deployment.
- E1 still requires pinning the exact Rady et al. Wi-Fi 6 profile and implementing the discrete-event network owner.
- Partial local-matrix Hungarian semantics remain intentionally deferred to E2.

### Next step
Run the corrected E0 locally. Do not start E1 until all conditions report exact zero gap, zero oracle mismatch, zero non-unanimous tasks, zero safety failures, and zero replay failures.

### Commit SHA
- optimizer owner: `ad9d72cf83d9f3f46f91e6fdd1893b47133135f8`
- optimizer tests: `2b45e430ee51754965019e6ba1bfb79196910fa1`
- protocol correction: `a520a9b617ee8c2037a1f2a287fe96bee58ad6de`
- zero-loss metric contract: `eb299ad0049b26468ce53cc836d82a157f06430b`
- protocol tests: `6eb3e4a9b5a2738d6c7500c092687c8abcb5ad26`
- E0 runner: `42cb4ab2ae4b607160eb32af20021c4c2f1c28d4`
- package export: `24b38758799673077049073896e7aefb03c1ca08`
- metric tests: `4ed0fdbd6ad1ced6aa13e25eecfccf111e337054`
- E0 result contract doc: `589d2cfe084ac8a9774d9a8a929e64af052d882e`
- README status update: `4af6478e6708a4a46580b35d52348073798e11e6`


## 2026-10-09 — Corrected E0 formal pass and E1 empirical latency implementation

### Purpose
Close E0 after the user's corrected formal local run and implement E1 as a trace-driven communication-time experiment using pinned ROS 2 Wi-Fi measurements.

### E0 verification result
- Unit tests: 12/12 passed.
- 500 corrected E0 scenarios.
- Every condition: gap 0, ASR 1, oracle mismatch 0, non-unanimous tasks 0, safety failures 0, replay failures 0.
- Corrected raw output: `results/e0_protocol_correctness/raw/e0_corrected_20261009T141508Z.csv`.
- Corrected summary: `results/e0_protocol_correctness/summary.csv`.
- These locally generated files remain pending user-side git commit.

### Files
- `democracy_mrta/network.py`
- `democracy_mrta/coordination.py`
- `democracy_mrta/__init__.py`
- `experiments/run_e1.py`
- `scripts/__init__.py`
- `scripts/prepare_rady_wifi_dataset.py`
- `tests/test_network.py`
- `tests/test_coordination.py`
- `data/external/.gitignore`
- `results/e1_latency/README.md`
- `README.md`
- `docs/EXPERIMENT_PROTOCOL.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions / owners
- `network.compute_git_blob_sha`: external data integrity owner.
- `network.verify_rady_dataset_bytes`: pinned source-data contract owner.
- `network.ensure_rady_dataset`: external dataset dependency owner.
- `network.load_rady_latency_profile`: empirical profile extraction/data validation owner.
- `network.summarize_latency_profile`: profile descriptive-statistics owner.
- `network.EmpiricalLatencySampler.sample_ms`: deterministic keyed empirical bootstrap owner.
- `coordination.simulate_ideal_full_information`: ideal timing reference owner.
- `coordination.simulate_leader_hungarian`: leader communication architecture timing owner.
- `coordination.simulate_full_view_hungarian`: decentralized full-view communication timing owner.
- `coordination.simulate_democracy_hungarian`: Democracy cost/vote/quorum/commit timing owner.
- `experiments.run_e1.simulate_methods`: E1 controlled-method orchestration owner.
- `experiments.run_e1.summarize_rows`: E1 aggregate result owner.
- `experiments.run_e1.write_selected_events`: designated audit event-log owner.

### Responsibility movement
Network evidence acquisition, integrity, profile extraction, and sampling now belong to `network`. Coordination timing belongs to `coordination`. Protocol voting correctness remains in `protocol`; the E1 simulator does not create a second protocol state machine.

### Preserved behavior
- Fixed Hungarian optimizer.
- E0 correctness contract.
- Strict-majority Democracy decision rule.
- Packet loss remains disabled in E1.
- Reliable initial task dissemination remains unchanged.

### Intentionally changed behavior
- E0 status moves from pending to passed based on the user's local corrected run.
- E1 now has executable trace-driven timing behavior.
- E1 primary network profile is pinned to Rady location 2 / ax_160mhz_6ghz / 120–181 s.
- Per-message latency is selected by deterministic keyed empirical bootstrap rather than constant/normal delay.
- Event logs default to designated audit seed 0 rather than all seeds to prevent unnecessary multi-million-row artifacts; aggregate metrics remain 100-seed.

### Network evidence / provenance
- Source repository: `minarady1/wifi_for_industrial_robotics`
- Commit: `1996e5bb69b9ba4d25060cbc14838ddedf65cff2`
- JSON Git blob: `11e70e685229cc26458f272b0c954487c87d7953`
- Profile: Medium range LoS (60 m), Wi-Fi 6E ax/6/160
- Steady-state samples: 121
- Mean 33.593687 ms; P50 19.962509 ms; P95 64.149866 ms; P99 159.419021 ms; max 531.535123 ms.

### Diagnostic contract
New network diagnostics:
- `network.verify_rady_dataset_bytes / data / RADY_DATASET_BLOB_MISMATCH`
- `network.ensure_rady_dataset / dependency / RADY_DATASET_MISSING`
- `network.ensure_rady_dataset / dependency / RADY_DATASET_DOWNLOAD_FAILED`
- `network.load_rady_latency_profile / data / RADY_DATASET_PARSE_FAILED`
- `network.load_rady_latency_profile / data / RADY_LOCATION_MISSING`
- `network.load_rady_latency_profile / data / RADY_CONFIG_MISSING`
- `network.load_rady_latency_profile / data / RADY_CONTROL_SERIES_MISSING`
- `network.load_rady_latency_profile / data / RADY_CONTROL_SERIES_LENGTH_MISMATCH`
- `network.load_rady_latency_profile / data / RADY_STEADY_PROFILE_EMPTY`

### Open risks
- E1 empirical bootstrap captures measured application-delay distribution but does not model new 802.11 MAC contention caused by a 100-robot fleet.
- Bootstrap samples are independent across logical messages in E1; temporal correlation is deferred to E7 trace replay.
- Payload-byte counts are logical protocol payload estimates, not full DDS/RTPS/UDP/IP on-air frame bytes.
- E2 still needs explicit partial-matrix feasibility and packet-loss semantics.
- E1 code has not yet been executed in the user's local environment.

### Next step
Run the complete test suite, prepare/verify the Rady dataset, and run E1 with 100 seeds. Inspect the communication-time scaling before implementing packet loss.

### Commit SHA
- network owner: `54721844ff322946a4c5def416ac9584b4f4ad7e`
- coordination owner: `6081df7a78277e7b5d294848ef2fd5a4cbd0df7e`
- network tests: `946457f4c3c1052ea5c92011a84c7fc866e0f0ec`
- coordination tests: `8ddc2b7688f4caa8b9b95c88fa7d9598c139c7d2`
- dataset preparation: `80e4d6fedc982b64aebdcd50925a652cd219072a`
- E1 runner: `8a090dff60d0cb63e128b8cd13c42bc9e7435f9c`
- package export: `7ed0c22d655f613e5fc69355c6eebf786a2d1a63`
- scripts package: `fedb4ed71fb6d753b25dab51939cc6dccd3459d0`
- README result/status update: `35f24cd8c80939d5b5fbb2cc569011b985ac26b6`
- canonical E1 semantics: `c703d27bacd2b07294fa0a230e2a157b730b3e45`


## 2026-10-09 — Portable verified HTTPS for Rady dataset download

### Purpose
Fix E1 external-dataset preparation on Python installations whose system/OpenSSL CA store cannot validate `raw.githubusercontent.com`, while preserving TLS certificate verification.

### Files
- `democracy_mrta/network.py`
- `requirements.txt`
- `tests/test_network.py`
- `results/e1_latency/README.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions / owners
- `network.build_verified_https_context`: owns construction of the verified HTTPS SSL context using the certifi CA bundle.
- `network.ensure_rady_dataset`: continues to own the external dataset download and now uses the verified context from the dedicated SSL-context owner.

### Responsibility movement
HTTPS trust-store construction is separated from dataset acquisition. Dataset provenance and Git blob verification remain owned by the existing network data-integrity functions.

### Preserved behavior
- HTTPS certificate verification remains enabled.
- The pinned Rady source URL, repository commit, and Git blob SHA are unchanged.
- Downloaded bytes still must pass `verify_rady_dataset_bytes` before being stored.
- No experiment, latency model, or protocol semantics changed.

### Intentionally changed behavior
- HTTPS verification now uses the `certifi` CA bundle instead of relying solely on the host Python/system CA store.
- `certifi>=2024.2.2` is now a declared runtime dependency.

### Diagnostic contract
New dependency failure:
- `network.build_verified_https_context / dependency / CERTIFI_NOT_INSTALLED`

Existing download failure remains:
- `network.ensure_rady_dataset / dependency / RADY_DATASET_DOWNLOAD_FAILED`

No insecure TLS fallback is permitted.

### Verification status
A unit test now requires the generated SSL context to keep hostname checking and certificate verification enabled. Local execution is pending the user's pull/install/rerun.

### Open risks
Corporate TLS interception or a custom private CA not present in certifi can still fail verification; such environments must explicitly install their trusted CA rather than disabling certificate checks.

### Next step
On the user's Mac: pull, install updated requirements, rerun the full test suite, then rerun `python3 -m scripts.prepare_rady_wifi_dataset`. If successful, proceed with E1.

### Commit SHA
- verified HTTPS context: `28051494a49d2096e068cd6f9776bbe093f7a609`
- certifi dependency: `e61c110446a72218361cb367d0640ffcf829e0e9`
- network test: `73b51e739ae63e6e25a2f102ac56b6cc86a46d20`
- E1 setup documentation: `7690a8ea9985ed703ada0ec36bea2018f936852d`


## 2026-10-09 — E1 transport correction: broadcast announcements

### Purpose
Correct the E1 communication topology after the first local pilot revealed that cost announcements and commit announcements were modeled as \(N-1\) unicasts rather than the protocol's intended logical wireless broadcasts.

### Pilot evidence
The user's first E1 run completed successfully with 18/18 unit tests and the pinned 121-sample Rady profile. The generated timing data are retained as diagnostic evidence only. In that obsolete model, 100R/100T Democracy reported 29,700 messages and Full-View 9,900 messages because broadcasts were expanded to per-peer unicasts.

### Files
- `democracy_mrta/coordination.py`
- `tests/test_coordination.py`
- `docs/EXPERIMENT_PROTOCOL.md`
- `README.md`
- `results/e1_latency/README.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions / owners
- `coordination._broadcast_event`: owns one logical wireless broadcast transmission.
- `coordination._unicast_event`: owns direct point-to-point transmission.
- `coordination._broadcast_cost_exchange`: owns one-broadcast-per-robot cost dissemination and local matrix-ready times.
- `coordination.simulate_leader_hungarian`: now uses cost unicasts plus one assignment broadcast.
- `coordination.simulate_full_view_hungarian`: now uses one cost broadcast per robot.
- `coordination.simulate_democracy_hungarian`: now uses cost broadcasts, direct vote unicasts, and one commit broadcast per task.

### Responsibility movement
No owner movement. The correction is inside the existing `coordination` transport/timing owner.

### Preserved behavior
- Same Hungarian optimizer.
- Same Rady latency profile.
- Same zero-loss E1 scope.
- Same strict-majority quorum.
- Same direct vote-to-candidate semantics.
- Same event-driven timing.

### Intentionally changed behavior
- A logical broadcast is now one attempted transmission/payload copy, not \(N-1\) unicast messages.
- Zero-loss E1 assigns one trace-derived latency sample to each logical broadcast and exposes that arrival to all peers simultaneously.
- Cost-row exchange message count changes from \(N(N-1)\) to \(N\).
- Democracy commit message count changes from \(N_T(N-1)\) to \(N_T\).
- Leader assignment dissemination changes from \(N-1\) unicasts to one broadcast.
- The 2026-10-09 first E1 timing run is explicitly non-paper pilot evidence and must be rerun.

### Diagnostic contract
No new error category or code. Broadcast/unicast mode is explicit in the event owner via `receiver_id == BROADCAST_RECEIVER_ID`.

### Open risks
- One-broadcast/one-latency E1 is a protocol-level model, not a receiver-specific Wi-Fi PHY/MAC broadcast experiment.
- E2 must explicitly define per-receiver delivery/loss behavior for a single broadcast transmission.
- Fleet-size-dependent shared-channel contention remains outside E1.

### Next step
Pull the broadcast correction, rerun the full tests, then rerun `python3 -m experiments.run_e1 --seeds 100`. Only that corrected E1 result should be entered as the formal paper result.

### Commit SHA
- coordination broadcast correction: `c7c8f0d4f9450544865c09f583155d5902944804`
- coordination tests: `019deefb18f03529789179bf041ee298f15f5e78`
- canonical protocol: `e29053177fb61cc62a4126ae1b131f689a50886f`
- README: `237f888fccc2aaf7f542eefd221891b5e3fe6f2c`
- E1 result ledger: `8b84cb31daa3c885b9b90d879e33e6339246e68a`


## 2026-10-09 — Corrected E1 formal trace-driven latency result

### Purpose
Record the broadcast-corrected 100-seed E1 result and close the latency-only experiment before adding packet loss.

### Files
- `README.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions
No code functions changed in this result-record commit.

### Verification result
The corrected E1 run completed for 10R/5T, 25R/10T, 50R/30T, 100R/50T, and 100R/100T with 100 seeds per condition.

Key 100R/100T means:
- Leader actionable/global: 477.408627 ms.
- Full-View actionable/global: 452.626633 ms.
- Democracy actionable: 478.326876 ms.
- Democracy global agreement: 918.550733 ms.
- Leader messages/payload: 100 / 81,600 bytes.
- Full-View messages/payload: 100 / 81,600 bytes.
- Democracy messages/payload: 10,100 / 401,200 bytes.
- Reference local Hungarian compute: 0.752068 ms.

### Interpretation
The dominant cost is communication, not Hungarian computation. Democracy's quorum adds only about 25–26 ms beyond Full-View actionable time in the larger conditions and is essentially latency-equal to Leader-Hungarian at 100 robots. The larger Democracy global-agreement time comes from waiting for all task commit broadcasts. Its principal cost is therefore communication volume and final dissemination rather than quorum decision latency.

### Responsibility movement
None.

### Preserved behavior
- broadcast-corrected cost/commit transport;
- direct vote unicasts;
- fixed Hungarian optimizer;
- zero packet loss;
- pinned Rady latency profile.

### Intentionally changed behavior
None; this entry records experimental evidence only.

### Diagnostic contract
No new diagnostics.

### Open risks
- The local raw/event/summary result files have not yet been confirmed committed to GitHub.
- E1 does not model additional shared-medium contention induced by 10,100 Democracy transmissions.
- E2 must define partial local-matrix semantics and packet-loss behavior before implementation.
- Commit loss remains a safety concern and must not be introduced into E2 until its safety semantics are explicit.

### Next step
Commit the corrected E1 raw, event, and summary files from the local machine. Then implement E2 with Bernoulli loss on cost and vote delivery while keeping commit dissemination reliable for safety; commit-loss localization remains a later explicit experiment after its safety contract is defined.

### Commit SHA
README E1 result record: `a3a804b717e66f6c3dfcfd6473b243c9591a6200`


## 2026-10-09 — E2 single-round Bernoulli packet-loss implementation

### Purpose
Implement the next formal experiment after E1: paired Bernoulli packet-loss sweeps over cost delivery and vote delivery while keeping commit dissemination reliable.

### Files
- `democracy_mrta/optimizer.py`
- `democracy_mrta/network.py`
- `democracy_mrta/protocol.py`
- `democracy_mrta/coordination.py`
- `experiments/run_e2.py`
- `tests/test_optimizer.py`
- `tests/test_network.py`
- `tests/test_protocol.py`
- `tests/test_coordination.py`
- `results/e2_packet_loss/README.md`
- `docs/EXPERIMENT_PROTOCOL.md`
- `README.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions / owners
- `optimizer.solve_visible_hungarian_assignment`: owns exact Hungarian optimization over only locally visible robot rows and may return a partial assignment.
- `network.validate_packet_loss_probability`: owns packet-loss probability validation.
- `network.BernoulliLossSampler.is_delivered`: owns deterministic keyed Bernoulli delivery.
- `protocol.find_unique_majority`: owns expected quorum/no-quorum resolution without converting ordinary no-quorum into an exception.
- `protocol.resolve_unique_majority`: preserves the E0 hard-failure boundary by wrapping `find_unique_majority`.
- `protocol.validate_one_to_one_commits`: owns committed-assignment safety validation.
- `coordination._lossy_broadcast_deliveries`: owns per-receiver delivery outcomes for one logical broadcast.
- `coordination._lossy_unicast_delivery`: owns lossy direct-message delivery.
- `coordination._simulate_lossy_cost_broadcasts`: owns receiver-local visible-row construction and cost-phase ready times.
- `coordination.simulate_leader_hungarian_lossy`: owns E2 Leader behavior.
- `coordination.simulate_full_view_hungarian_lossy`: owns E2 strict complete-view behavior.
- `coordination.simulate_democracy_hungarian_lossy`: owns E2 partial-view proposal, lossy vote, quorum and reliable commit timing.
- `experiments.run_e2.result_row`: owns per-seed E2 metrics.
- `experiments.run_e2.summarize_rows`: owns condition-level E2 summaries.
- `experiments.run_e2.write_audit_records`: owns designated-seed logical-message and receiver-delivery audit evidence.

### Responsibility movement
No existing responsibility was wrapped or duplicated. Partial optimization belongs to `optimizer`, delivery/loss belongs to `network`, majority/safety belongs to `protocol`, and experiment-specific method timing/orchestration remains in `coordination`.

### Preserved behavior
- static one-to-one assignment model;
- deterministic Hungarian implementation;
- fixed strict-majority quorum denominator;
- Rady empirical latency profile;
- logical broadcast message counting from corrected E1;
- reliable initial task/epoch announcement;
- reliable commit dissemination for this experiment.

### Intentionally changed behavior
- Cost packets and Democracy vote packets may now be lost independently.
- One logical cost broadcast has receiver-specific Bernoulli delivery outcomes.
- Missing rows are never imputed from ground truth.
- Local Hungarian proposals may be partial when visible robot rows are fewer than tasks.
- A voter abstains on tasks omitted by its partial assignment.
- No-quorum is recorded as timeout instead of raising an E0-style protocol error.
- Full-View now requires every robot to have the complete matrix in E2.
- Leader may produce a partial assignment from its received rows.
- E2 intentionally performs one round only; retry count is zero.
- Commit loss remains out of scope until its duplicate-execution safety contract is specified.

### Timeout contract
The E2 phase timeout equals the largest measured latency in the pinned E1 profile: 531.535123 ms. If all expected costs arrive, a robot proceeds at its actual last-arrival time; if at least one expected row is missing, it closes the cost phase at the timeout. The vote deadline is one phase-timeout interval after the latest local proposal-ready time.

### Diagnostic contract
New diagnostics:
- `optimizer.solve_visible_hungarian_assignment / state / NO_VISIBLE_ROBOTS`
- `optimizer.solve_visible_hungarian_assignment / data / VISIBLE_ROBOT_ID_OUT_OF_RANGE`
- `optimizer.solve_visible_hungarian_assignment / contract / PARTIAL_HUNGARIAN_CARDINALITY_MISMATCH`
- `network.validate_packet_loss_probability / data / INVALID_PACKET_LOSS_PROBABILITY`
- `protocol.find_unique_majority / safety / MULTIPLE_QUORUM_WINNERS`
- `protocol.validate_one_to_one_commits / safety / DUPLICATE_ROBOT_COMMIT`
- `protocol.validate_one_to_one_commits / safety / DUPLICATE_TASK_COMMIT`

### Verification status
Code and regression tests are committed. The assistant execution container cannot resolve github.com, so the repository test suite could not be executed there. Formal verification is pending the user's local test run.

### Open risks
- E2 uses independent receiver-level Bernoulli loss; correlated/burst loss remains E5.
- Broadcast delay is one shared trace-derived latency per logical broadcast while delivery is receiver-specific.
- E2 does not model additional 802.11 contention from Democracy's high vote volume.
- Full-View is intentionally a complete-information baseline and may collapse quickly as fleet size/loss rises.
- No retry behavior is evaluated in E2.
- Commit-loss safety remains unresolved and isolated from this experiment.

### Next step
Run the full local unit suite, then run `python3 -m experiments.run_e2 --seeds 100`. Verify the (p=0) compatibility boundary before interpreting higher loss levels.

### Commit SHA
- partial-view optimizer: `18e014cb5808d615144de5897c32c62db66ff5a6`
- Bernoulli loss owner: `ae0e6a1fe8e395a15fbe8b9e015201655112bb34`
- protocol quorum/safety boundaries: `79fa6f2795154ba4e0cbafed769f6a9c5ea1ea9e`
- lossy coordination: `0eac39e489e4cb4d4ced1b1a5461a371c5a17d8d`
- optimizer tests: `054485df417e1cadd9ce5cbaa75fe4177714356a`
- network tests: `7f1eb3caaf209e54ab9f0bea908aa7387813701c`
- protocol tests: `99495ebcbea1b09f65a5d3472eb2e898c68b567f`
- coordination tests: `ac02e039f8e8245d06c8fae4b44cbbc41982e197`
- E2 runner: `1dc166c0cab17f21a223167dc8b2467f029f9bb8`
- E2 result ledger: `632c36fb53704de90c567894e0cfb258392d26a0`
- canonical protocol: `338445d757925c2adc58c0bbe7142251e5d77c74`
- README: `4f751d5944e7143d2f0e3e8e06e5d31b23aa058b`


### E2 documentation-rendering follow-up

No experiment semantics or code behavior changed. Math rendering in the E2 README/canonical/result ledger was corrected after the implementation entry so that loss probabilities, timeout, and quorum notation display unambiguously.

Latest documentation commits:
- README E2 rendering: `33d1f6cee58dfe7483708eeba1137531248bdac1`
- canonical E2 rendering: `7fc245304f34c79c4b7e25b7e9a0ae2fe6af69b0`
- E2 result-ledger rendering: `b70f480080da66924aa33e18eead3342ff0ee67a`


## 2026-10-09 — E2 CER instrumentation after first 100-seed pilot

### Purpose
Add task-level correct-executor metrics after the first formal-sized E2 run revealed that assignment completion alone can hide severe quality degradation under partial information.

### Pilot evidence
The user's local suite passed 28/28 tests. The first 100-seed E2 run completed all five robot/task conditions and six loss levels with zero safety failures.

Representative pilot findings:
- 100R/50T, 10% loss: Democracy task commit 0.9762, full success 0.39, successful full-assignment gap 0.012795%; Leader full success 1.0 but optimal rate 0 and gap 8.497465%.
- 100R/50T, 30% loss: Democracy task commit 0.1522; Leader full success 1.0 but gap 37.787330%.
- 50R/30T, 10% loss: Democracy task commit 0.945667 and successful gap 0.144397%; Leader full success 1.0 but gap 9.280371%.
- All reported safety failures were zero.

The pilot is not the final paper E2 because it cannot evaluate correctness of partial committed outcomes.

### Files
- `democracy_mrta/metrics.py`
- `tests/test_metrics.py`
- `experiments/run_e2.py`
- `docs/EXPERIMENT_PROTOCOL.md`
- `README.md`
- `results/e2_packet_loss/README.md`
- `docs/CHANGE_CONTINUITY.md`

### Functions / owners
- `metrics.evaluate_assignment_correctness`: owns task-level comparison against the deterministic complete-information Hungarian oracle.
- `experiments.run_e2.result_row`: records correct/incorrect committed tasks and CER fields.
- `experiments.run_e2.summarize_rows`: aggregates CER and conditional correctness across paired seeds.

### Responsibility movement
No protocol, optimizer, network, or coordination responsibility moved. This change is measurement-only. Correct-executor evaluation belongs to the existing metrics owner.

### Preserved behavior
- Same scenarios and seeds.
- Same Bernoulli delivery.
- Same Rady latency profile.
- Same partial-view Hungarian behavior.
- Same quorum.
- Same reliable commit assumption.
- Same one-round/no-retry E2 protocol.
- Same timing and message counting.

### Intentionally changed behavior
No allocation behavior changed. E2 output now additionally records:
- `correct_committed_tasks`;
- `incorrect_committed_tasks`;
- `correct_executor_rate`;
- `correctness_among_committed`.

The first 100-seed E2 output is reclassified as diagnostic pilot evidence; a CER-instrumented rerun is required for the paper result.

### Metric definitions
- CER = correct committed tasks / total tasks.
- correctness among committed = correct committed tasks / committed tasks.
- When committed tasks = 0, conditional correctness is NaN.

### Diagnostic contract
New metrics diagnostics:
- `metrics.evaluate_assignment_correctness / data / INVALID_TOTAL_TASKS`
- `metrics.evaluate_assignment_correctness / contract / ORACLE_ASSIGNMENT_INCOMPLETE`
- `metrics.evaluate_assignment_correctness / contract / DUPLICATE_TASK_IN_EVALUATED_ASSIGNMENT`
- `metrics.evaluate_assignment_correctness / data / COMMITTED_TASK_OUT_OF_ORACLE_RANGE`

### Open risks
- Full-View in E2 is a strict one-shot complete-view baseline and should not be described as a retransmitting/gossip implementation.
- CER uses the deterministic complete-information Hungarian assignment as the reference executor map; alternate equal-cost global optima may be scored as different executors if ties occur.
- E2 still does not model MAC contention, burst loss, retry policy, or commit loss.

### Next step
Pull the CER instrumentation, run the unit suite, and rerun E2 with the same 100 seeds. Use CER plus task commit rate as the primary robustness-quality plot before closing E2.

### Commit SHA
- metrics owner: `7afed145945e5e248d9685d310c652e4f713f1a4`
- metrics tests: `3a9b440975b89c3c183d74b6f92e338b691ced7e`
- E2 runner: `abac777719f69ed1840acee517e9797f2fcebd6b`
- canonical metric update: `459fc4b3e56c16d53bd895e30244aeaf4601dc03`
- README status update: `4d0dbd44919e8963a70ef78e1ac4f0232c13ae25`
- result ledger update: `aeb989833c274bc210aac23800ceb65d6b73986a`


## 2026-10-09 — E2 vote-level forensic instrumentation (no protocol behavior changes)

### Purpose
The user challenged the 100R/50T, 30% cost-loss + 30% vote-loss result: 70.285 mean visible rows, yet only 15.22% task commits. Earlier 30/30 tests and aggregate metrics do not establish how many local proposals actually match the Hungarian oracle, how many raw votes each candidate earned, or whether the second lossy hop destroyed an otherwise available quorum. Mark the E2 result UNDER AUDIT until ballot evidence is cross-checked.

### Changed files
- `democracy_mrta/coordination.py`
- `democracy_mrta/metrics.py`
- `experiments/audit_e2_votes.py`
- `tests/test_metrics.py`
- `docs/EXPERIMENT_PROTOCOL.md`
- `README.md`
- `docs/CHANGE_CONTINUITY.md`

### Responsibility owners / named functions
- `coordination.simulate_democracy_hungarian_lossy`: adds an optional read-only capture flag for already-computed local views/proposals and actual counted vote ledgers; no new voting logic.
- `coordination.snapshot_counted_vote_ledgers`: serializes the existing protocol ledger for forensic comparison; no new ledger/state machine.
- `metrics.require_e2_vote_audit`: requires explicit opt-in capture.
- `metrics.index_e2_vote_deliveries`: indexes actual vote transport observations without resampling delivery.
- `metrics.verify_e2_vote_ledgers`: cross-checks reconstructed delivered+self-votes against the protocol's existing ledger and actual commit winners.
- `metrics.evaluate_e2_vote_audit`: compares actual local assignments to the same complete-information Hungarian oracle and produces voter/task/candidate vote audit rows.
- `experiments.audit_e2_votes.run_vote_audit`: runs paired existing scenario/sampler/simulator over selected seeds and exports CSVs.
- `experiments.audit_e2_votes.aggregate_seed_summaries`: reports exact counts for pre-transport majority, post-transport majority, and quorum lost during vote transmission.
- `experiments.audit_e2_votes.aggregate_robot_rows`: aggregates each voting robot's proposals, correct proposals, and delivered/dropped votes across seeds.

### Responsibility movement
None. Coordination remains the protocol timing/transport owner. Metrics owns audit verification and calculation. The new experiment script only orchestrates calls to existing owner functions and writes audit evidence; it is not an alternate protocol implementation.

### Preserved behavior
- Cost packet loss and vote packet loss remain separate keyed independent Bernoulli trials.
- Same `p_loss` for both hops in the default E2 sweep.
- Same partial visible-row Hungarian proposals and missing-row semantics.
- Same strict majority `Q=floor(N/2)+1`.
- Same self-vote bypass of network transport, reliable commit, and no-retry E2.
- No changes to optimizer, packet-loss sampler, voting/commit logic, timing, official run_e2 output columns, or seeds.

### Intentionally changed behavior
- An **opt-in audit-only** simulator argument `capture_vote_audit=True` exposes immutable snapshots of already-computed voter local views/proposals and actual counted vote ledger in the result object.
- Audit runner now exports `summary.csv`, `seed_summary.csv`, `voters_by_seed.csv`, `voters_summary.csv`, `tasks_by_seed.csv`, and a selected seed's `candidates_seedNNN.csv`.
- README and canonical protocol mark the 30%-loss performance result not paper-accepted until audit review.

### Diagnostic contract
- `metrics.require_e2_vote_audit / contract / E2_AUDIT_NOT_CAPTURED`
- `metrics.index_e2_vote_deliveries / contract / E2_AUDIT_DUPLICATE_VOTE_DELIVERY`
- `metrics.evaluate_e2_vote_audit / contract / E2_AUDIT_ORACLE_INCOMPLETE`
- `metrics.evaluate_e2_vote_audit / contract / E2_AUDIT_LOCAL_VIEW_MISMATCH`
- `metrics.evaluate_e2_vote_audit / contract / E2_AUDIT_INVALID_LOCAL_PROPOSAL`
- `metrics.evaluate_e2_vote_audit / contract / E2_AUDIT_MISSING_VOTE_PACKET`
- `metrics.evaluate_e2_vote_audit / contract / E2_AUDIT_UNEXPECTED_VOTE_PACKET`
- `metrics.verify_e2_vote_ledgers / contract / E2_AUDIT_LEDGER_MISMATCH`
- `metrics.verify_e2_vote_ledgers / contract / E2_AUDIT_QUORUM_MISMATCH`

### Verification status
Five unit tests added: zero-loss self/unicast accounting, full-loss local self-vote accounting, read-only capture noninterference, corrupted-ledger detection, missing-audit detection. GitHub edits were committed, but the assistant container cannot resolve github.com for full repo checkout and **has not executed** the new test suite or forensic 100-seed run. User-side execution is required before claiming correctness.

### Open risks
- Actual 100-seed per-task/per-voter ballot rates are not present in the uploaded console log. Audit still needs to be run locally.
- 30% missing rows do not imply 30% incorrect multi-task Hungarian ballots; the ballot distribution must be measured.
- Existing multi-task independent task-level quorum may produce assignment conflicts under untested adversarial cases; current `validate_one_to_one_commits` detects but does not repair them. This remains a separate safety-contract issue.
- The E2 paper claim must remain pending until audit results establish the first lost-quorum boundary.

### Next step
Run `python3 -m unittest discover -s tests -v`; then `python3 -m experiments.audit_e2_votes --robots 100 --tasks 50 --p-loss 0.3 --seeds 100`. Inspect `summary.csv` and `tasks_by_seed.csv`, compare task commit rate against the original 15.22% and verify zero ledger-contract failures. Analyze raw oracle support versus delivered oracle votes. Only then decide whether there is an implementation defect or an expected consequence of fragmented proposals and the second transport loss.

### Commit SHA
- coordination opt-in snapshots: `bf521720f05fe05d301a52ac2d9e0ce6830dabfc`
- metrics forensic validation: `00d0389e85bf0e23bef4c2a27c903231845628b5`
- audit runner: `8645e4a709a0ef1c2bc6e4c37acf9b9567e09a33`
- audit regression tests: `b5d30840894dbbf3da92a8682ba6263d0b9324af`
- canonical audit gate: `bb1cbf1f0d8d60e720265d7abd9d33a213167411`
- README result status: `b6a44bd2382f9aa0a01b7645447b9743e8ecf08a`


### Follow-up: individual ballot evidence and audit-owner separation

The same E2 forensic measurement concern was extended without changing allocation semantics:
- `metrics.E2VoteAuditReport.ballots` now contains each generated voter/task/candidate ballot with oracle match, visible rows, self-vote flag and delivery outcome.
- The selected audit seed is exported to `ballots_seedNNN.csv`.
- `metrics.verify_e2_local_views` owns source-information validation.
- `metrics.collect_e2_ballot_evidence` owns cross-indexing existing proposals against actual vote transport observations.
- `metrics.summarize_e2_task_vote_support` owns per-task and per-candidate statistics.
- `metrics.summarize_e2_ballot_totals` owns per-seed aggregate metrics.
- `metrics.evaluate_e2_vote_audit` is reduced to explicit orchestration of these named boundaries.
- `experiments.audit_e2_votes.run_vote_audit` remains only the audit-runner owner.

New owner diagnostic mapping:
- `metrics.verify_e2_local_views / contract / E2_AUDIT_LOCAL_VIEW_MISMATCH`
- `metrics.collect_e2_ballot_evidence / contract / E2_AUDIT_INVALID_LOCAL_PROPOSAL`
- `metrics.collect_e2_ballot_evidence / contract / E2_AUDIT_MISSING_VOTE_PACKET`
- `metrics.collect_e2_ballot_evidence / contract / E2_AUDIT_UNEXPECTED_VOTE_PACKET`
All previously documented diagnostic codes remain the same.

Files: `democracy_mrta/metrics.py`, `experiments/audit_e2_votes.py`, `tests/test_metrics.py`, `docs/EXPERIMENT_PROTOCOL.md`, and this continuity record. The canonical document now specifies the ballot-level evidence contract.

Preserved behavior: all existing algorithm states, votes, random loss samples, quorum outcomes, timing and official E2 metrics.

Verification remains pending user's local test/audit execution.

Follow-up commits:
- metrics individual ballots: `8e831e0425f647c368971f1ee222f2b7b95555ed`
- audit runner ballot CSV: `359536e2f0e2b847b8bdc084858c9f07fb7011e6`
- tests individual ballots: `759586fa8852e46412ef348c4fb212534e4b346b`
- canonical ballot evidence: `202c9f47144852d92e234d3a475e330cd622a9ab`
- modular metrics audit functions: `aa0a5d582359b4ee61a3ef027b9e6cf61288b338`


## 2026-10-10 — E2 controlled cost-row-loss threshold sweep (independent vote loss override)

### Purpose
Support a loss-threshold experiment where each robot receives independently incomplete local cost information as cost packet loss grows, while Democracy vote transmission remains fully reliable. This isolates local-Hungarian proposal disagreement from a second lossy transport hop without changing the earlier E2 experiment.

### Files changed
- `democracy_mrta/coordination.py`
- `experiments/run_e2.py`
- `tests/test_coordination.py`
- `tests/test_run_e2.py`
- `docs/EXPERIMENT_PROTOCOL.md`
- `README.md`
- `results/e2_packet_loss/README.md`
- `docs/CHANGE_CONTINUITY.md`

### Named functions / owner boundaries
- `coordination.simulate_democracy_hungarian_lossy`: optional `p_vote_loss` override applies only to remote vote unicast Bernoulli delivery; original `p_loss` still applies to each robot's peer cost reception. When `p_vote_loss is None`, vote loss inherits `p_loss` exactly as before.
- `network.validate_packet_loss_probability`: existing data validation owner; reused by the coordinator for a non-None override and by the runner for CLI-configured probabilities.
- `experiments.run_e2.simulate_methods`: E2 method orchestration forwards the optional vote loss to Democracy, leaving Leader/Full-View unchanged.
- `experiments.run_e2.result_row`: records effective `p_vote_loss` along with legacy `p_loss` (cost loss).
- `experiments.run_e2.summarize_rows`: groups results by robot count, task count, cost loss, effective vote loss, and method.
- `experiments.run_e2.write_audit_records`: adds `p_vote_loss` to emitted per-seed network audit CSV records.
- `experiments.run_e2.main`: parses `--vote-loss-probability` and selects the effective vote loss per cost-loss point; same paired seed, scenario and latency/profile behavior.

### Responsibility movement
None. Packet loss sampling and probability validation remain in `network`; proposal, voting and quorum stay in existing `coordination`/`protocol`; the E2 runner controls experiment parameters and reporting. No wrapper or second voting/state machine.

### Preserved behaviors
- Legacy `python3 -m experiments.run_e2 --seeds 100` produces the same decisions and packet outcomes: cost and vote loss each equal the swept `p_loss`, sampled independently with distinct keyed events.
- Hungarian, quorum, self-vote, commit reliability, event timing, no retries, seed handling and cost-row visibility unchanged.
- Leader, Full-View and Ideal method algorithms unchanged.
- Existing `p_loss` column, existing output fields and their meanings unchanged.

### Intentionally changed behaviors
- Optional CLI argument `--vote-loss-probability 0` makes Democracy's remote vote channel lossless across the cost-loss sweep.
- More generally, any fixed `--vote-loss-probability` in [0,1] can be used.
- E2 outputs add `p_vote_loss` to raw CSV, summary, designated event logs, and concise console result lines; the legacy `p_loss` field now remains explicitly identified as the cost-loss variable.
- Recommended separate output root `results/e2_cost_only_100r50t` prevents overwriting prior formal E2 outputs.
- Cost-only sweep 100R/50T, 100 paired seeds, 0%-70% cost loss in 2-point increments, vote loss 0%.

### Diagnostic contract
Existing network validation error is preserved and reused:
- `network.validate_packet_loss_probability / data / INVALID_PACKET_LOSS_PROBABILITY`.

New regression tests check:
- cost-only delivery leaves local views and proposals unchanged relative to equal-p-loss E2;
- vote-only 100% loss preserves full cost information but destroys majority;
- absent vote override is byte/decision-equivalent to explicitly setting `p_vote_loss=p_loss`;
- runner transports the override to the actual coordinator and summarizes the two independent rates separately.

### Verification
GitHub commits completed. The assistant execution container cannot resolve github.com for a repository checkout. New tests and the sweep have **not been executed** here; the user must run the unit suite and a small smoke before accepting results. Do not claim a loss threshold until the new simulation outputs have been reviewed.

### Open risks
- First-loss-rate classified unusable depends on the explicitly chosen operational threshold (e.g. task commit <90%, <50%, <10%). Full-assignment optimality alone becomes too strict for multi-task cases.
- The earlier 30%/30% E2 results remain under ballot audit; the cost-only sweep does not retroactively validate them.
- Possible adversarial multi-task duplicate executor commitments remain a separate safety-contract risk; no repair or new coordination state was added.
- Existing E2 ignores MAC contention, commit loss, burst loss and retries, so the observed one-round threshold is not a deployed-network availability guarantee.
- The existing formal runner does not embed its Git SHA in every CSV row; capture the actual HEAD externally along with output paths.

### Next step
Run unit regressions. Smoke the independent loss flags, then run the 100R/50T 0-70%-cost-loss sweep with vote loss set to zero in an isolated output root; inspect task commit, CER and global optimality independently and report all predefined practical cutoffs.

### Commit SHA
- coordinator loss override: `2357c35dac5983c31ee73d6bd808dc578bb52f5a`
- E2 runner independent parameters: `e749ffef49155755a497a39b8e054c3684292094`
- coordinator regression tests: `30c575be44a5db9bb3790fba7c8a7cb35db6b6c5`
- E2 runner regression test: `7259e20692ac6fe0b5f21be52452ea2b085c44a4`
- canonical protocol: `57b60f016b8d817db8ce640434bab18b371d0441`
- README commands: `ebafa19b428c1f5f5376ecde9ca4d88b5b66d23b`
- E2 result ledger: `e1a740c78f194f985e02a8263700658166e71b06`


## 2026-10-10 — Opt-in multi-round Democracy with committed executor retirement

### Purpose
Implement the user's corrected multi-task lifecycle: a robot that wins a task by majority reliably broadcasts a commit, becomes unavailable as both a future voter and candidate, and immediately starts executing its assigned task in the abstract protocol. Remaining unassigned robots continue voting only on remaining tasks in a new epoch. This is a NEW multi-round protocol mode, not a correction to the original one-round E2 benchmark.

### Files changed
- `democracy_mrta/protocol.py`
- `democracy_mrta/coordination.py`
- `experiments/run_e2_retirement.py`
- `tests/test_retirement.py`
- `docs/EXPERIMENT_PROTOCOL.md`
- `README.md`
- `results/e2_retirement_100r50t/README.md`
- `docs/CHANGE_CONTINUITY.md`

### Exact owner modules and named functions
- `protocol.initialize_retirement_membership`: validates fleet/task sizes and creates the initial immutable per-epoch eligibility snapshot.
- `protocol.apply_announced_retirement_commits`: exclusively owns the epoch-to-epoch membership transition. After reliable commit announcements, removes the committing executor from eligible voters and candidates and removes its assigned task from the pending task pool. Rejects an ineligible executor/task, and invokes the existing `protocol.validate_one_to_one_commits` safety boundary on the aggregate assignment.
- `coordination.validate_epoch_identity_mapping`: validates original physical/global robot/task IDs for a compact active epoch. Does not permit duplicate IDs.
- `coordination.map_epoch_local_proposal`: maps compact optimizer row/task indices to stable physical robot/task IDs before a proposal becomes a vote.
- `coordination._lossy_broadcast_deliveries` and `coordination._simulate_lossy_cost_broadcasts`: broadcast cost rows only among active robots, sampling each physical sender/receiver link independently per epoch. Internally convert physical recipient IDs to compact local-visible-row indices.
- `coordination._unicast_event`, `coordination._broadcast_event`: append the epoch ID to empirical latency sampling keys **only for rounds >0**, retaining E2's round-0 bootstrap keys unchanged.
- `coordination._lossy_unicast_delivery`: records epoch ID in vote delivery observations while maintaining the existing keyed Bernoulli sampling contract.
- `coordination._summarize_lossy_result`: computes actual physical commit costs from compact-row/task matrices when original ID mapping was provided, while preserving the default unmodified path.
- `coordination.simulate_democracy_hungarian_lossy`: remains the ONLY owner of per-round Hungarian/packet/vote/quorum/commit execution. Optional physical robot/task identity mappings let this existing owner run on a shrinking team with fresh epoch ID and a strict majority of the frozen current electorate. All prior default arguments still mean the same single-round E2.
- `coordination.build_retirement_round_cost_matrix`: constructs exactly the active-row/pending-column submatrix for the next epoch; never re-inserts retired robots or completed tasks.
- `coordination.require_retirement_commit_announcements`: checks each newly committed pair is represented by a reliable commit broadcast before retirement.
- `coordination.simulate_democracy_hungarian_retirement`: genuinely new owner of bounded multi-round scheduling and cumulative timing; delegates every epoch to `simulate_democracy_hungarian_lossy` and membership changes to `protocol.apply_announced_retirement_commits`. Does not duplicate the vote/majority state machine.
- `experiments.run_e2_retirement.retirement_result_row`: per-seed final oracle/CER/coverage/latency comparisons including the original first-round E2 result.
- `experiments.run_e2_retirement.retirement_round_rows`: per-epoch voter IDs, pending tasks, dynamic quorum, committed pairs and timing evidence.
- `experiments.run_e2_retirement.summarize_retirement_results`: grouped paired-seed summary.
- `experiments.run_e2_retirement.write_retirement_audit_events`: designated seed 0 physical-ID/logical-transmission/receiver-delivery audit with round IDs and absolute time offsets.
- `experiments.run_e2_retirement.run_retirement_experiment`: standalone experiment orchestration, provenance, CSV outputs. Does not alter E2's official runner.

### Responsibility movement
No prior responsibility moved. Existing packet loss/delay owners remain network; partial optimization remains optimizer; distinct ballot counting/strict majority remain protocol. Protocol now additionally owns persistent membership eligibility, while coordination owns the new per-round scheduling lifecycle. No second vote ledger or state machine is introduced.

### Preserved behavior
- Original E2 CLI, its fixed electorate, one-round/no-retry contract, published results, prior output paths, Hungarian solver, strict majority, losses, benchmark comparison methods and measurements remain unchanged unless the new entrypoint is explicitly invoked.
- First retirement epoch with identical seed/loss/latency input is *exactly* the original E2 Democracy epoch in vote counts, events and decisions; the zero-loss path completes in one round.
- Independent Cost Loss and Vote Loss remain controlled by their own Bernoulli draws. Task announcement and post-quorum commit remain reliable for this experiment.
- No changing of the quorum denominator in the middle of an epoch, no accepting stale votes from prior epochs, no duplicate robot or task assignment.

### Intentionally changed behavior (new experimental mode only)
- Each epoch starts from a frozen set of active voters/candidates and pending tasks. Its majority is `floor(active_robots/2)+1`.
- Once a candidate wins a task, the simulator records its reliable commit; **only after the entire epoch finishes and all commits are broadcast** does the next epoch exclude the assigned robot and task.
- Unresolved tasks are reconsidered in the next epoch using fresh cost broadcasts and fresh independently keyed losses. If no task commits, the same eligible population retries with a higher round ID until `max_rounds`.
- New rounds use original physical robot/task IDs for sampling, votes and announces; compact optimizer indices never leak as public IDs.
- The main objective is eventual task coverage / final oracle-matched executors and the cost/time/message penalty compared with the paired first-round baseline.
- Physical task motion, execution duration, return to duty and later rejoining are NOT represented; 'start executing' means committed/unavailable for further allocations.

### Diagnostic contract
- `protocol.initialize_retirement_membership / data / INVALID_RETIREMENT_TEAM_SIZE`
- `protocol.apply_announced_retirement_commits / state / RETIREMENT_COMMIT_NOT_ELIGIBLE`
- `protocol.validate_one_to_one_commits / safety / DUPLICATE_ROBOT_COMMIT` and `DUPLICATE_TASK_COMMIT` retained and applied to aggregate epochs.
- `coordination.validate_epoch_identity_mapping / data / INVALID_EPOCH_ID_MAPPING`
- `coordination.require_retirement_commit_announcements / contract / RETIREMENT_COMMIT_ANNOUNCEMENT_MISMATCH`
- `coordination.simulate_democracy_hungarian_retirement / data / INVALID_RETIREMENT_ROUND_LIMIT`
- Existing `network.validate_packet_loss_probability / data / INVALID_PACKET_LOSS_PROBABILITY` reused.
- Existing no-quorum outcome is still an expected state, NOT a raised exception.

### Tests / verification
Added `tests/test_retirement.py` covering:
1. announced commit removes exactly its executor/task for next round;
2. retired robot cannot commit again;
3. a single robot cannot be committed to two tasks;
4. controlled 4R/2T first round with only one task committed, then subsequent 3R/1T quorum shrinking 3 -> 2 and avoiding the retired robot in packets;
5. a no-quorum epoch followed by successful re-vote with a higher epoch ID;
6. zero-loss first epoch exactly equals original E2 behavior;
7. one-epoch cap preserves pending tasks;
8. invalid max-round limit raises correct diagnostic;
9. independent keyed Bernoulli first round matches original E2 packet events/decisions exactly.
There were 39 passing local tests BEFORE this change according to the user; the added 9 tests have NOT been run in this assistant's environment. External GitHub checkout fails DNS in the assistant's container; user-side local execution is required. Do not claim correctness of new implementation until tests and smoke pass.

### Open risks
- Dynamic membership relies on the strong E2 assumption that commit announcements reach everybody before the next epoch. Distributed delivery loss/partitions can create divergent voter membership and need a separate membership-agreement protocol.
- Each epoch has a frozen voting population; opportunistic asynchronous mid-epoch retirement is intentionally NOT implemented.
- Quorum shrinking does not mathematically guarantee new agreement, and can weaken agreement thresholds; packet retransmission/retry count and latency may be expensive. Terminate after `max_rounds` even if pending tasks remain.
- Sequential irreversible commits can reach full task coverage but cost more than the one-shot full-information Hungarian oracle. Compute total-cost gaps only for full final assignments.
- Static assignment simulator cannot verify real execution/movement/completion or robot later becoming available.
- Bernoulli delivery independence and pinned E1 empirical latency omit shared-radio contention, burst loss, and commit loss.
- Existing 30%/30% E2 forensic ledger audit is still outstanding and unaffected by the new mode.
- Runtime SHA and UTC time are recorded by the new experiment runner, but the source network dataset pin is documented in canonical experiment spec rather than repeated in every raw row.

### Next step
Run the full Mac local test suite and then the 3-seed smoke. Verify first-round results agree with the existing E2 under paired Cost Loss/Vote Loss and confirm round records have decreasing eligible/pending populations, updated quorum, no duplicate assignments, and no stale voter packets. Only then run a 100-seed Cost-only loss sweep and evaluate final coverage, CER, full-assignment optimality, message cost and elapsed time against the original single-round E2.

### Commit SHA
- persistent protocol membership: `b5b09b5043a8b29406da819a2d48d13504dc1acc`
- round-keyed physical identity and event support: `a7044db33f013da96e2e26821fc4b6b34afbf72b`
- physical-ID local proposal/majority integration: `58a51a6848f24fda10390537c7ae37122b5894cf`
- bounded multi-round coordinator: `133724ee15df933a2204f0b26e82fbe3341c538c`
- paired identity mapping/diagnostic cleanup: `9b4d2c4a8d3bba35f29c6e58f3794f1ff702674e`
- experiments runner: `53813d69116e5c16a49c2eefb755ce9c55ed4062`
- safety/transition/rounding regression tests: `dfc1e7b2aa3ab216e1cf0c2e77a3c11e3f3c66bc`
- first-round exact E2 regression: `ed7805790d2459189a4e1f941aae92a0e70fb82`
- canonical spec: `e19e83d2074eaaf4ddfe2c47ae609df65487a6fd`
- README: `4f2f39510e2aa6c373cbd4748f1c09d100acb215`
- result ledger: `6320ab35e7290fe362a9d5f76e64d41f2fb50c1b`
