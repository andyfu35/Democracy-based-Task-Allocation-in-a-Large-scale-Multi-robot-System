# P2D One-Shot Centralized Method Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Price Auction in a NEW P2D four-method comparison with one-shot, no-retransmission **Centralized Method**, using the identical locally-visible Global Greedy assignment rule as Proposed Method and a dashed full-information quality reference.

**Architecture:** Keep all original P2-C, P2 and P1 executable methods and their source-verified raw records immutable. Add a focused native Centralized runtime that pays for physically emitted but dropped Cost unicast frames, a read-only source-attestation extension in the existing baseline registry, a dedicated P2D formal runner, and a new plotting owner. New primary figures compare Proposed Method / CBAA / CBBA / Centralized Method; full-info Greedy is a separate offline reference, not a network participant.

**Tech Stack:** Python 3, `unittest`, existing `democracy_mrta` causal shared-medium model, Rady latency calibration, GitHub provenance, CSV/JSON/SVG.

**Spec:** `docs/superpowers/specs/2026-10-14-p2d-centralized-one-shot-comparator-design.md`.

## Global Constraints

- Exact protocol `N=T=100`, capacity one, paired seeds `0..99`, loss probabilities `0,0.1,...,0.9`, **100 seeds per level**; no Cost retransmission or recovery and no oracle leakage.
- Coordinator is fleet robot `0`, using its own Cost row locally; robots `1..99` emit exactly **one 816-byte Cost unicast** to coordinator per run, before receiver-specific Bernoulli drop. Emission-time radio occupancy and application sender bytes count regardless of receipt.
- One external reliable TASK announcement (physical framing), one reliable assignment publication, and one reliable Commit per awarded executor; no second decision epoch. Reliable control is an explicit **existing modeling assumption**, not a claim about all-lossy real RF. No extra ACK/retry simulation.
- Planner reuses `democracy_mrta.optimizer.solve_visible_batched_greedy_assignment` with only received-on-time cost rows, sorted by physical robot ID to preserve the `(cost,task_id,robot_id)` tie rule; no Hungarian decisions.
- Source-verify the exact original P2-C Voting user ZIP SHA256 `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055` (Git `8038370205d586c697295b42eb255812be7aa88e`, Voting per-seed raw SHA256 `a5f6c59837b80596066752c6546a37a387b4ccf177f8d4f1c03c527309a4a5fe`) and external original P2 ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9` (Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`).
- Only **1,000 new Centralized** cases, plus **3,000 SHA-pinned reused Proposed/CBAA/CBBA** cases; no Price Auction in new plots, and NO mutation of original P2-C, P2, P1 code or evidence.
- Required owner/function diagnostic first-failure boundaries using only `data,time,state,dependency,planning,safety,runtime,contract`; include useful expected / actual / details.
- Every functional code stage includes an appended `docs/CHANGE_CONTINUITY.md` entry for its own functions, preserved/changed behavior, diagnostics, risks, next step, and commit SHA; append P2D canonical protocol in `docs/EXPERIMENT_PROTOCOL.md` as soon as behavior is implemented.
- The user runs Mac local tests and 100-seed formal study; **do not claim PASS or publish new performance numbers until they are actually verified**.

## Review Focus

1. **Subtle Cost-row leakage:** a dropped or post-cutoff remote row must never appear in the planner; Task 1's `test_hidden_cost_rows_never_used` constructs an adversarial cheap dropped row.
2. **Zero-loss physical tie order:** sorted local row indices must be correctly mapped to physical robot IDs; Task 1's `test_zero_loss_exact_full_info_pairs` exercises ties.
3. **No falsely cheap lost packets:** p=1 emits exactly 99 Cost unicasts and pays their airtime, sender bytes and deadline; Task 1's `test_all_dropped_still_pays_airtime_and_stop`.
4. **Tampered archive or mismatched seeds:** reject before any new method simulation, not after output creation; Task 2's source SHA, CSV and scene-hash failure tests and Task 3's preflight test.
5. **Missing success-quality cohort:** never plot quality as zero for 0-success Centralized levels and never call guard/partial stop `successful allocation time`; Task 4's `test_empty_success_quality_is_gap`.

---

### Task 1: One-Shot Centralized Native Protocol

**Files:**
- Create: `democracy_mrta/centralized_method.py`
- Test: `tests/test_p2d_centralized_method.py`
- Modify: `docs/EXPERIMENT_PROTOCOL.md` (new isolated P2D contract section)
- Modify: `docs/CHANGE_CONTINUITY.md` (native owner milestone, with implementation commit SHA)

**Interfaces:**
- `validate_centralized_configuration(*, cost_matrix, coordinator_id: int, loss_probability: float, cost_cutoff_ms: float) -> tuple[int, int]`.
- `collect_one_shot_cost_rows(*, cost_matrix, coordinator_id: int, cost_start_ms: float, cutoff_ms: float, sampler: WifiCausalTimingSampler, loss_sampler: BernoulliLossSampler, p_loss: float) -> CentralizedCostReceipt` with `physical_visible_rows`, `cost_events`, `cost_deliveries`, `cost_sender_bytes`, `cost_sender_sends`, `cost_phase_end_ms`.
- `plan_from_received_cost_rows(*, receipt: CentralizedCostReceipt) -> tuple[tuple[int,int], ...]` (physical `(robot_id,task_id)` pairs).
- `publish_centralized_assignment(*, pairs, release_ms, sampler, coordinator_id: int) -> CommunicationEvent`; exactly one actual native `_broadcast_event` and actual size-aware payload (header + 8 bytes/pair, at most 1200B); no hidden assignment oracle.
- `emit_centralized_commits(*, pairs, release_ms, sampler) -> tuple[CommunicationEvent,...]`; one true emitted Commit/pair with deterministic chronology and original one-to-one safety check.
- `simulate_one_shot_centralized(*, cost_matrix, task_positions, profile, seed: int, p_loss: float, coordinator_id: int=0) -> CentralizedResult`; `CentralizedResult` exposes `assignment`, `task_coverage`, `native_success`, `native_stop_ms`, `cost_deliveries`, `sender_sends`, `sender_bytes`, `receiver_attempts`, `receiver_drops`, `event_ledger`, `phase_times`, `stop_reason`. Use the same task frame encoder/actual owner and the same 144Mbps modeled network.
- Reuse `coordination._unicast_event` + `_lossy_unicast_delivery`, `coordination._broadcast_event`, `network.WifiCausalTimingSampler.sample_packet_ms`, `optimizer.solve_visible_batched_greedy_assignment`, `protocol.validate_one_to_one_commits`; do not fork existing planners or timing/loss engines.

- [ ] **Step 1: Write failing focused tests** in `tests/test_p2d_centralized_method.py`: `test_cost_one_send_per_noncoordinator_no_retry` asserts `n-1` cost sends (99 for formal `n=100`), payload `16+8*n`, and exactly one assignment publication; `test_zero_loss_exact_full_info_pairs` checks deterministic physical pairs (including equal-cost ties); `test_hidden_cost_rows_never_used` asserts p=1 only coordinator own row visible; `test_all_dropped_still_pays_airtime_and_stop` verifies sender bytes, positive airtime/phase stop and no refunded transmission; `test_partial_cannot_claim_full_completion` checks coverage and one-to-one Commit safety; `test_late_cost_row_is_excluded` checks cutoff; `test_invalid_loss_and_duplicate_assignments_have_named_diagnostics` checks owner/function/category/code.
- [ ] **Step 2: Run RED**: `python3 -m unittest tests.test_p2d_centralized_method -v`. Expected: missing module/tests fail before implementation.
- [ ] **Step 3: Implement exact named functions** above, preserving the existing causal transport owner. Cost unicast events must be scheduled before `_lossy_unicast_delivery`. For p=1 there is no artificial data repair. Reliable TASK/assignment/Commit occur exactly once, never sent again; no repeated epochs.
- [ ] **Step 4: Run GREEN and regressions**: `python3 -m unittest tests.test_p2d_centralized_method tests.test_e9g_wifi_timing tests.test_p2_packet_loss -v`. Expected: all pass.
- [ ] **Step 5: Record contract** in `docs/EXPERIMENT_PROTOCOL.md`, update `docs/CHANGE_CONTINUITY.md`, commit as `feat(p2d): add one-shot centralized native owner`. Record SHA in continuity (a follow-up doc commit can record the exact SHA if needed).

### Task 2: Immutable P2-C Voting and P2 Baseline Source Verification

**Files:**
- Modify: `experiments/p2_baseline_reuse.py` (the existing real archive owner, not a duplicate wrapper)
- Test: `tests/test_p2d_source_reuse.py`
- Modify: `docs/CHANGE_CONTINUITY.md`

**Interfaces:**
- Add `read_verified_p2c_voting(archive_path: Path, percentages: tuple[int,...], first_seed: int, seeds: int) -> tuple[list[dict],dict]`; load only **original user** P2-C Voting per-seed rows from its source-pinned ZIP and verify source manifest, checksum, `n=100`, `m=100`, capacity1, 10-level grid, seed geometry and unique method-key. Do NOT accept a P2-C plotting CSV or generated archival remix as raw evidence.
- Reuse unchanged `read_verified_original_baselines` (which may include immutable Price Auction rows); select **only CBAA/CBBA** after source verification for this P2D study.
- Add `merge_p2d_paired_evidence(*, voting_rows, native_baselines, centralized_rows, percentages, first_seed, seeds, p2c_source_sha: str, p2_original_sha: str, centralized_source_sha: str) -> list[dict]`; exactly one `voting,cbaa,cbba,centralized` record per seed/loss, identical `scene_sha256`, unchanged original field values plus explicit `source_git_sha/source_role`.

- [ ] **Step 1: Write failing tests**: `test_reject_modified_p2c_zip_before_results`, `test_reject_mismatched_manifest_or_partial_grid`, `test_require_same_seed_scene`, `test_old_baselines_preserved_field_for_field`, `test_no_price_auction_in_new_four_method_rows`.
- [ ] **Step 2: Run RED**: `python3 -m unittest tests.test_p2d_source_reuse -v`.
- [ ] **Step 3: Implement two named source functions** in `experiments.p2_baseline_reuse` without altering old original archive functions.
- [ ] **Step 4: Run GREEN**: `python3 -m unittest tests.test_p2d_source_reuse tests.test_p2_packet_loss -v` (plus real original ZIP fixture verification when available).
- [ ] **Step 5: Append named function source-contract continuity** and commit `feat(p2d): source-pin P2-C voting and paired original baselines`.

### Task 3: Dedicated Formal P2D Runner and Source-Safe Metrics

**Files:**
- Create: `experiments/run_p2d_centralized.py`
- Test: `tests/test_p2d_runner.py`
- Modify: `docs/EXPERIMENT_PROTOCOL.md`, `docs/CHANGE_CONTINUITY.md`

**Interfaces:**
- `validate_config(args: argparse.Namespace) -> tuple[int,...]` freezes `p=0..90` in 10% steps, 100 seeds for formal and exactly two original ZIP paths.
- `prepare_evidence(args, source_sha: str, losses: tuple[int,...]) -> tuple[list[dict], dict]`: new result root, append-only raw CSV + fsync, immutable config SHA, strict same-SHA/same-prefix `--resume`.
- `run_one_centralized_case(scene, profile, p_loss: float) -> dict`: invoke Task 1 native; return original-compatible method fields with `method="centralized"` plus native `committed_task_count` and `task_coverage`. Set completed-only assignment quality only when `native_success`. Full-info per-seed Greedy cost must be computed by existing optimizer ONLY in read-only metrics, never passed to Centralized native owner.
- `validate_complete_grid(rows, losses, seed_start, seeds, methods) -> None`: exactly `1000` new Centralized rows and `4000` merged rows, source/scene match, genuine incomplete methods unchanged; zeros never substituted for missing native time/bytes.
- `summarize(rows, losses) -> list[dict]`: `40` rows, native complete rate, modeled native stop mean/all 100, sender bytes mean/all 100, mean coverage, completed-only `cost/full_info_greedy_cost` and explicit `quality_sample_count`; no four-way success intersection as the primary quality denominator (Centralized may be zero).
- `write_evidence(...)`, `main(argv=None)` write new-source CSVs, SHA-pinned manifest, environment and source provenance; invoke figure owner from Task 4 for the final formal figure.

- [ ] **Step 1: Write failing tests**: `test_formal_grid_requires_100_seeds_and_two_pinned_archives`, `test_missing_or_tampered_archive_rejected_before_new_emission`, `test_1000_plus_3000_exact_methods`, `test_zero_loss_native_pairs_match_full_info_reference`, `test_centralized_partial_cost_has_no_full_quality_value`, `test_resume_rejects_modified_sha_or_config`, `test_failing_original_time_is_not_imputed_zero`.
- [ ] **Step 2: Run RED**: `python3 -m unittest tests.test_p2d_runner -v`.
- [ ] **Step 3: Implement runner functions** above, never invoking Price Auction or rewriting P2-C original raw; all emulated SEND time includes dropped attempts.
- [ ] **Step 4: Run GREEN**: `python3 -m unittest tests.test_p2d_runner tests.test_p2d_source_reuse tests.test_p2d_centralized_method -v`.
- [ ] **Step 5: Append experiment canonical and continuity**, then commit `feat(p2d): add isolated paired one-shot centralized study runner`.

### Task 4: Dedicated P2D Four-Panel Figure with Black Full-Info Dashed Reference

**Files:**
- Create: `experiments/p2d_plot.py`
- Test: `tests/test_p2d_plot.py`
- Modify: `docs/CHANGE_CONTINUITY.md`

**Interfaces:**
- `validate_p2d_plot_source(summary: list[dict], losses: tuple[int,...]) -> None`: require the four expected method labels/10 PL levels, 100 denominators, actual natively complete quality counts.
- `render_p2d_figure(summary: list[dict], losses: tuple[int,...]) -> str`: editable native SVG four panels; labels **Proposed Method**, **CBAA**, **CBBA**, **Centralized Method** only; render a thin **black dashed** `Full-Info Baseline=100%` in A and `Full-Info Baseline=1.0` in D, no fictional B/C zero reference. B/C logarithmic y, all-seed stop/bytes, receiver-loss inclusive. D uses method-own success-only quality and `n`, missing quality means a **gap**, not zero.
- Optional separate `render_p2d_task_coverage_figure` if needed for high-loss Centralized partial progress; the `mean_task_coverage` CSV must exist regardless.

- [ ] **Step 1: Write failing tests**: `test_only_four_new_method_labels`, `test_black_dashed_full_info_reference_is_only_a_and_d`, `test_empty_success_quality_is_gap`, `test_no_price_auction_anywhere_in_svg`, `test_loss_coincident_curves_not_shifted`, `test_bad_seed_denominator_diagnostic`.
- [ ] **Step 2: Run RED**: `python3 -m unittest tests.test_p2d_plot -v`.
- [ ] **Step 3: Implement actual `p2d_plot` owner**; do not edit or relabel original P2-C publication SVG or `experiments.p2_packet_loss_plot`.
- [ ] **Step 4: Run GREEN**: `python3 -m unittest tests.test_p2d_plot tests.test_p2_packet_loss -v`.
- [ ] **Step 5: Append figure-contract continuity** and commit `feat(p2d): add full-info dashed reference to native comparator plot`.

### Task 5: Final Acceptance and Mac 100-Seed Handoff

**Files:**
- Modify: `docs/EXPERIMENT_PROTOCOL.md` (ensure frozen final P2D semantics and same-source limits)
- Modify: `docs/CHANGE_CONTINUITY.md`
- Optionally create: `docs/P2D_ONE_SHOT_CENTRALIZED.md` for concise local reproduction, only if canonical section becomes too unwieldy
- Test: existing `tests/test_p2d_*.py` and full unittest suite

**Interfaces:** CLI must accept `--formal --seeds 100 --p2c-voting-zip PATH --original-p2-zip PATH --output-root NEW_ROOT` and should accept `--losses 0.00 --seeds 2` as a bounded smoke mode (with verified archives).

- [ ] **Step 1: Run syntax and all targeted checks**: `python3 -m compileall -q democracy_mrta experiments tests`; `python3 -m unittest discover -s tests -p 'test_p2d*.py' -v`.
- [ ] **Step 2: Run complete repository regression suite**: `python3 -m unittest discover -s tests -v` and report any inherited/unrelated failures by exact test name, never silently claim all-pass.
- [ ] **Step 3: Mac zero-loss gate** after original user ZIPs are present: `python3 -m experiments.run_p2d_centralized --losses 0.00 --seeds 100 --p2c-voting-zip "$HOME/Downloads/p2c_global_greedy_100seed.zip" --original-p2-zip "$HOME/Downloads/p2_loss10_100seed.zip" --output-root "results/p2d_zero_$(date +%Y%m%d_%H%M%S)"`. Require 100/100 exact physical Global Greedy pairs; no nonzero loss can be merged into this zero-loss acceptance.
- [ ] **Step 4: Mac formal 100-seed run** in NEW root: `python3 -m experiments.run_p2d_centralized --formal --seeds 100 --p2c-voting-zip "$HOME/Downloads/p2c_global_greedy_100seed.zip" --original-p2-zip "$HOME/Downloads/p2_loss10_100seed.zip" --output-root "results/p2d_formal_$(date +%Y%m%d_%H%M%S)"`. Package `per_seed_p2d.csv`, `summary_p2d.csv`, `p2d_four_panel.svg`, config and SHA256 manifest, run log for independent audit.
- [ ] **Step 5: Verify P2D immutable evidence gates** (1k new + 3k read-only sourced, 4k/40 grouped, 0%-loss exact, full info denominator, one-shot 99 Cost SEND, no retransmission, sender bytes/airtime charged on drops, success/quality sample denominators). Update both READMEs and plot links **only after** audit and leave P2-C historical result cited honestly.
- [ ] **Step 6: Final continuity entry/commit** with purpose, exact files/functions, ownership/responsibility moves, preserved/changed behavior, full diagnostic contracts, current risks, next experiment, SHA of each functional commit; do not present unrun tests as passing.

## Self-Review & Handoff Checklist

- Every design section maps to a tested task: yes (native, source, runner, plot, acceptance).
- Named type/field/interface owners are exact across task boundaries; external client tests exercise hidden-state and no-retry constraints.
- Original Python tests and immutable source-identity archives remain untouched by the new method.
- New P2D comparator is intentionally **one-shot**; an abrupt high-loss completion collapse would describe this configuration only, not all centralized MRTA.
- **Execution environment limitation:** the current assistant container cannot resolve `github.com` for git clone; GitHub connector can commit source text. Full code/test execution may require the user's Mac and must be reported as such.
