# Hsien-Te Methods (P2J-v3) — One-shot probabilistic voting with paid completion fallback

**Branch:** `experiment/p2j-v3-completion-fallback-20261022`  
**Official publication name: Hsien-Te Methods.** This name describes the original `probabilistic_complete_fallback` native algorithm; the original study `P2J_V3_DETERMINISTIC_FALLBACK_PAIRED`, original code SHA `33bd5f771b347365d768890ea71e87f0c1e7c6a3`, and raw data IDs are unchanged. Uploaded formal ZIP SHA256 `9839901650acc1d2feba0a14158a55c1211796a486bfc6c2d5fd9c8ac358e710` contains 3,000 native cases/30 groups, independently audited with its manifest. The Hsien-Te subset achieved native full 100-task allocation in all 1,000 cases under E0 generalist-robot and reliable Score/Commit assumptions; PL30 global Greedy cost gap −6.01% and PL90 +35.65%. Main Figure2 publication (five arms) commit `c7f8876c6c6e332423590d8a38b1244bb5e937b7`; provenance in main `docs/HSIEN_TE_FIGURE2_COMPARISON_AUDIT.md`. Historical P2J-v1/v2 and original four-arm SVG remain archived; no RF hardware guarantee is implied.

## Frozen protocol and assumptions

All 100 robots may execute all 100 tasks, capacity=1, one task per robot. Cost is sent once per robot (per-recipient Bernoulli loss), Vote is sent once per robot (one compact PVOT aggregating 100 task-uniform/local-Softmax tickets, tau=5; independent per-recipient loss). A candidate counts only its own votes and physically delivered timely remote Vote tickets. Each positive candidate sends a paid reliable PSCR announcing only its own positive Vote counts and own Cost, delivered to all BEFORE matching. Each actually assigned executor sends its own paid reliable Commit. No retransmitted Cost/Vote, no extra Score message and no new decision epoch.

### Owner: post-Score task allocation

Keep the P2J-v2 global maximum-cardinality matching on **certified positive** PSCR edges, then its signed margin / votes / candidate-own-Cost preference. Independently verify the certified maximum bipartite Score matching. Only after this proof, P2J-v3 optionally fills unmatched tasks by sorting unassigned task IDs and available robot IDs, pairing by ascending ID. The fallback robot may have zero Vote and NO announced Cost for that task. **No hidden full-information Cost is used to select fallback**. Realized Cost is computed AFTER native Commit from the original E0 scene solely for offline audit.

For positive-Score maximum `K+`, fallback count `F`, and total committed `K`: 

```text
K+ = certified_score_max_matching
F  = completion_fallback_count = 100-K+
K  = K+ + F = 100      (under 100 generalist robots / 100 tasks / reliable Commit)
native_total_cost = native_supported_cost + measured_fallback_cost
```

Model assumptions are essential. This is not a guarantee for heterogeneous robot skills, infeasible tasks, failure to execute, a non-generalist team, or lossy Score/Commit on real radios. Every added Commit is a REAL sender-charged frame; no artificial 100% overwrite.

### Actual responsibilities and first diagnostics

- `coordination.validate_probabilistic_batch_scope` validates the `completion_policy` (none / idle_robot_id), one original Cost, one Vote, one epoch; rejects fallback on non-probabilistic methods with `contract/P2J_V3_FALLBACK_REQUIRES_PROBABILISTIC_VOTE`.
- `coordination.validate_probability_score_view` validates certified Score and allowed policy with `data/P2J_V3_UNKNOWN_COMPLETION_POLICY`.
- `coordination.resolve_dynamic_probability_margin_winners` retains original P2J-v2 certified Score maximum-cardinality optimization and `planning/P2J_SCORE_GLOBAL_CARDINALITY_MISMATCH` independent proof.
- `coordination.complete_unassigned_score_matching` solely owns deterministic zero-Score completion from unused robot/task IDs. First possible failures include `contract/P2J_V3_INVALID_POSITIVE_SCORE_MATCH`, `planning/P2J_V3_INSUFFICIENT_IDLE_CAPACITY`, `contract/P2J_V3_POSITIVE_MATCH_LEFT_UNUSED`, `contract/P2J_V3_COMPLETION_POSTCONDITION`. No second state machine.
- Original `coordination.simulate_greedy_batch_vote_epoch` and retirement run Score->Commit with each added original paid Commit. A read-only `completion_fallback_pairs` native field preserves evidence.
- `experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case` forwards policy and physical trace without a new planner.
- `experiments.run_p2j_probabilistic_batch` owns 3-arm paired seed evidence, all Cost/Vote/Score/Commit SEND/Byte audit and offline fallback Cost, including first failure `contract/P2J_V3_CERTIFIED_SCORE_COMPLETION_CONTRACT` or `contract/P2J_V3_FALLBACK_NATIVE_TRACE_MISMATCH`.

Error categories remain data/time/state/dependency/planning/safety/runtime/contract, with owner/function/category/code/expected/actual/details.

## Exactly three comparable native methods

- `one_batch_greedy` — unchanged original single-batch wireless Greedy.
- `probabilistic_global_margin` — P2J-v2 original positive-Score maximum matching, **no fallback**.
- `probabilistic_complete_fallback` — P2J-v3 same Softmax, packets and initial matching, deterministic unmatched-task completion, paid additional Commit.

100 robots, 100 tasks, capacity 1; seeds 0..99 paired on scene hash; packet loss 0..90% at 10% increments, focus 30%. Original Rady latency data + hypothetical 144Mbps shared wireless medium. Track whole-allocation success (100/100 tasks), average coverage, complete-success-only relative full-information Global minimum-pair Greedy Cost, all-seed time/Bytes, count/identity/cost of zero-Score fallback, and Score maximum matching. DO NOT replace incomplete cost gap by zero. Formal study ID is `P2J_V3_DETERMINISTIC_FALLBACK_PAIRED`; **3,000 fresh native cases, 30 groups**. Never overwrite old P2J-v2 original 2,000 cases.

## Mac — tests, Smoke, 30% 100-Seed gate, full formal

From the repository root, first update and run focused and full tests:

```bash
git fetch origin
git switch experiment/p2j-v3-completion-fallback-20261022
git pull --ff-only
git rev-parse HEAD
python3 -m compileall -q democracy_mrta experiments tests &&
python3 -m unittest discover -s tests -p 'test_p2j*.py' -v &&
python3 -m unittest discover -s tests -v
```

Smoke (0%,30%,90% ×2 seeds×3 methods=18 cases):

```bash
P2J_SMOKE="results/p2j_v3_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2j_probabilistic_batch \
  --losses 0.00,0.30,0.90 --seeds 2 \
  --votes-per-voter 100 --temperature 5.0 --margin-rule absolute \
  --output-root "$P2J_SMOKE"
```

Then 30% loss ×100 seeds×3 methods = 300 cases:

```bash
P2J_PL30="results/p2j_v3_pl30_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2j_probabilistic_batch \
  --losses 0.30 --seeds 100 \
  --output-root "$P2J_PL30"
```

Only after all tests/smoke/PL30 succeed, 0..90% formal ×100 seeds×3 methods = 3,000 cases:

```bash
set -o pipefail
P2J_FORMAL="results/p2j_v3_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2j_probabilistic_batch \
  --formal --seeds 100 --votes-per-voter 100 \
  --temperature 5.0 --margin-rule absolute \
  --output-root "$P2J_FORMAL" 2>&1 | tee "$P2J_FORMAL.log"
```

Require `P2J_COMPLETE rows=3000 groups=30` and manifest, then package:

```bash
test -f "$P2J_FORMAL/manifest_p2j.json" &&
zip -j "$HOME/Downloads/p2j_v3_complete_100seed.zip" \
  "$P2J_FORMAL/per_seed_p2j.csv" \
  "$P2J_FORMAL/summary_p2j.csv" \
  "$P2J_FORMAL/run_config_p2j.json" \
  "$P2J_FORMAL/manifest_p2j.json" \
  "$P2J_FORMAL.log"
shasum -a 256 "$HOME/Downloads/p2j_v3_complete_100seed.zip"
```

Send first full failing traceback instead of continuing on an error. The 100% completion target is a hypothesis until all native per-seed outcomes and physical ledger hashes are checked.
