# P1 — Five original allocators, one paired capacity-one measurement boundary

**Status (2026-10-13): FORMAL 1,500-CASE ORIGINAL ZIP RECEIVED AND INDEPENDENTLY VERIFIED (0 audit errors).** The frozen original preregistration below is retained for exact methodological provenance. [Completed formal P1 source analysis](P1_FORMAL_100SEED.md). No CI. This study is the one bounded acceptance experiment selected in [Research Closure Plan](RESEARCH_CLOSURE_PLAN.md). Do not replace historical E9I/J/L/M/N data; they remain separate original measurements.

## Fixed formal contract (freeze before observing results)

| Field | Preregistered setting |
|---|---|
| Robot/task sizes | N=T=25, 50, 100; capacity=1 |
| World / travel | Deterministic common 100m x 100m positions from `generate_e0_scenario(seed,N,N)`; Euclidean cost, speed 1m/s, service time 0 |
| Paired Seeds | Same scenarios 0..99 for each N/method |
| Loss | p=0.30 per native eligible physical receiver for method-native lossy packets; reliable source TASK/Score/Commit as originally specified |
| Time | Rady ROS application delay + **assumed** shared-medium 144 Mbps proxy, no actual measured Wi-Fi or ns-3 |
| Guard | Native CBAA/Price Auction/CBBA 160; **original Voting's established max 300**. Voting Multi-task runs original 1 epoch/task, no new guard |
| Original methods | `voting`, `cbaa`, `price_auction`, `voting_multitask`, `cbba` (this exact order); exclude team-authored Paid CBAA |
| Price settings | Original native epsilon=10m, task-home BID/AWARD original 28B wire and stage window formula |
| Original Voting | Frozen guarded Cost once + adaptive positive received-plurality Vote; Cost30/Vote30; paid reliable Score and Commit |
| CBAA | Original full bid/winner vector and local-certification stop; unpaid simulator all-local halt |
| CBBA | Original two-phase bundle/path consensus; observer agreement, no paid termination |
| Voting Multi-task | Original corrected candidate-only Vote unicast; task-level cost/score and paid commit, capacity constrained to one |

Historical Price Auction native implementation came from Git blob `2d2f1c0eaff94143ce256eebf0a0ee30603d8cba` on branch `experiment/e9l-distributed-price-auction`, because it was absent from the current experiment branch. **This source is restored inside its true owner `democracy_mrta.price_auction`, not reimplemented in an experiment wrapper.** The original Rady+Wi-Fi 28B Price Auction timing helper is also restored verbatim into the true `democracy_mrta.network.estimate_e9l_price_auction_stage_ms` owner. The only change to native Price code is an optional read-only observer callback that is default `None` and cannot change BID/AWARD/stop decisions. Native price packets, cost input, epsilon and algorithm are preserved.

## Two separate timestamps, never conflate them

1. `first_feasible_ms`: *external read-only first observed complete, globally unique C1 assignment after a physically incurred original communication phase.* Native original state is copied as immutable `(robot_id, task_id)` tuples; evaluator checks one robot per task, no duplicate task, all N tasks, and a monotonically nondecreasing timestamp. The first such timestamp is recorded once and **is NEVER fed back as an agent action, correction, stop/Commit/consensus ACK, or free protocol message**. Missing early evidence stays blank; a method can be feasible before its own stop or first feasible without its native local stopping proof.
2. `native_stop_ms`: method's original modeled stop / guard; full reliable paid Commit is a **different guarantee** from CBAA/Price locally certified + free all-local halt and CBBA external observer. Each result records `native_stop_reason`, the real sender SEND/Bytes, native delivery attempts/drops when available, failure/guard/censor, original packet ledger and original executed SHA. No post-hoc backfill of full network traffic or invented timestamp is allowed.

Native observation integration is bounded to the *true owners* of those snapshots:

- `coordination.simulate_democracy_hungarian_retirement` **unchanged**; original immutable `RetirementRoundTrace` is read by `experiments.run_e9h_adaptive_deadline.run_e9h_original_voting_case` opt-in observer, and each original reliable Commit/round end timestamp is replayed without changing retirement state.
- `democracy_mrta.cbaa.simulate_cbaa` optional `external_observer=None` after completed native consensus waves; `experiments.run_e9j_cbaa_vs_e9i.run_e9j_original_cbaa_case` opt-in p_loss and observer forwarding; defaults retain historical frozen behavior.
- `democracy_mrta.price_auction.simulate_price_auction` optional observer after actual physical BID and AWARD waves, reading only native TaskHome winners.
- `democracy_mrta.cbba_multitask.run_cbba` optional observer after actual received consensus snapshots are applied.
- `democracy_mrta.voting_multitask.run_voting_multitask` optional observer after physically paid reliable Commit.
- `experiments.run_e9m_multitask.run_e9m_case` forwards optional observer only when provided; E9M defaults and prior original results unchanged.
- `experiments.p1_feasibility.FirstFeasibleObserver.observe` owns read-only external timestamp/unique C1 check, `assess_euclidean_assignment` owns an **independent external Euclidean/Hungarian evaluation**. No second allocator state machine and no privileged agent input.
- `experiments.run_p1_matched_five` owns orchestration, scenario/source checks, reporting and original provenance. `experiments.p1_plot` owns SVG rendering only.

At capacity1, E9M discounted reward is *not* equal to an ordinary Euclidean Hungarian sum. Common external cost is `sum(math.dist(robot,task))`, independent optimal cost from `optimizer.solve_hungarian_assignment` and ratio `external_cost/oracle_cost`. This scorer **never chooses** the native assignment. Native fail or guard remains in the 100-Seed denominator. The additional `same_success_quality_p1.csv` reports quality **only across common seeds where ALL FIVE original allocators natively complete**, and reports the restricted denominator for each N/method. Do not present these conditional quality means as unconditional.

## Evidence and first-owner diagnostic contract

Native execution creates **1,500 original method-case rows** (`3 N × 100 Seeds × 5 methods`), append+fsync `per_seed_p1.csv`, `summary_p1.csv`, `same_success_quality_p1.csv`, `five_original_matched_comparison.svg` (one four-panel comparison), and `manifest_p1.json` with Git SHA, method config, original Price source blob, exact bytes SHA256 for all evidence files and all original success/failure/guard counts. New output directory only, original ZIPs/figures never overwritten. E9I/J/L remain true fresh native runs here, **not** the frozen old aggregates from E9N.

Named first-failure boundaries:

| Owner/function | Category / code | Trigger |
|---|---|---|
| `p1_feasibility.FirstFeasibleObserver.observe` | `time/P1_NONCAUSAL_OBSERVER_TIMESTAMP` | Phase timestamp nonmonotonic/nonfinite |
| `p1_feasibility.FirstFeasibleObserver.observe` | `data/P1_INVALID_NATIVE_SNAPSHOT` | Snapshot not immutable pair tuples |
| `p1_feasibility.assess_euclidean_assignment` | `contract/P1_BELOW_HUNGARIAN_OPTIMUM` | Reported assignment beats independent Hungarian oracle illegally |
| `run_p1_matched_five.validate_config` | `contract/P1_FORMAL_CONFIG_NOT_FROZEN` | Formal changes N, Seeds, native guards or loss |
| `run_p1_matched_five.verify_one_scene` | `contract/P1_SCENE_GEOMETRY_NOT_MATCHED` | Native vs historical E0 scenario mismatch |
| `run_p1_matched_five.run_original_auction` | `contract/P1_AUCTION_PACKET_ACCOUNTING` | Physical sender Bytes/SEND mismatch |
| `run_p1_matched_five.run_matched_case` | `contract/P1_NATIVE_SUCCESS_NOT_EXTERNAL_FEASIBLE` | Native terminal success but read-only final snapshot incomplete |
| `run_p1_matched_five.run_matched_case` | `time/P1_FIRST_FEASIBLE_AFTER_NATIVE_STOP` | Impossibly late observer feasibility |
| `run_p1_matched_five.validate_complete_grid` | `contract/P1_INCOMPLETE_OR_DUPLICATE_GRID` / `P1_PAIRED_SCENE_SHA_MISMATCH` | Missing, duplicate or mismatched paired source |
| `p1_plot.validate_plot_source` | `contract/P1_FIGURE_SOURCE_GRID_INCOMPLETE` | Not exactly 3×5 original summary/conditional quality entries |

Native method `ProtocolError` retains the original owner/function/category/code as a failed original row. If a native exception prevented returning an auditable packet ledger, its time/Bytes remain **missing**, not zero or imputed, and formal results require investigation before a time-ranking publication. Observer assessment errors must propagate; they must not be mistaken for a native method failure. No `E9K` Paid CBAA or external STOP wrapper is added.

## User-local Mac preflight and formal run — NO CI or Codex execution

From the repository root at branch `experiment/e9m-cbba-multitask`:

```bash
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p1_*.py' -v
python3 -m unittest discover -s tests -p 'test_e9m_*.py' -v
python3 -m unittest discover -s tests -p 'test_e9n_*.py' -v
```

Smoke: use the five genuine methods, all at once. Never skip an error and publish an incomplete run:

```bash
python3 -m experiments.run_p1_matched_five \
  --sizes 25 --seeds 2 --loss 0.0 \
  --output-root "results/p1_zero_smoke_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p1_matched_five \
  --sizes 25,50,100 --seeds 2 --loss 0.30 \
  --output-root "results/p1_loss30_smoke_$(date +%Y%m%d_%H%M%S)"
```

Formal, only after original-owner invariance and Smoke tests pass:

```bash
set -o pipefail
P1_ROOT="results/p1_matched_five_loss30_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p1_matched_five \
  --formal --sizes 25,50,100 --seeds 100 --loss 0.30 \
  --output-root "$P1_ROOT" 2>&1 | tee "$P1_ROOT.log"
test -f "$P1_ROOT/manifest_p1.json" && \
zip -r "$HOME/Downloads/p1_matched_five_100seed.zip" "$P1_ROOT" "$P1_ROOT.log"
```

Please provide the resulting original ZIP. The README A/B/C/D accepted plots do **not** change until independently verified full original P1 data arrive. This P1 test closes common **external measurement** fairness, NOT equal real distributed paid-finalization guarantee. Do not claim actual Wi-Fi latency or generalize to C4.


## Executed original formal source acceptance (2026-10-13)

Original ZIP `p1_matched_five_100seed_20261013_122905.zip` SHA256 `d2f30bf39d1f4aff336a5b7220a4f15ee887d0d79ccc8c8a536819f40691de58`, executed Git `24e002695748e976c7b2abdfce661431839c4a7b`, contains all fixed three-size × 100 Seeds × five native methods (1,500 original cases) with no missing rows. All source member SHA, original 300 seeded scene fingerprints, 1,500 Hungarian/original assignment/ledger checks, 15 source summary rows and 15 same-success quality rows and 1,500 Terminal events independently agree (0 audit errors). Original 1476 native success and 1478 externally observed feasible; 24 original Auction guard limitations remain recorded. Source original ZIP kept unchanged in personal Library `/投票演算法/P1/`; original run image and publication-only adjusted figure separately SHA-attested. CBAA and CBBA output identical final assignments in all 300 paired scenes and have different first feasible/native stop time order at N100. [Full verified result](P1_FORMAL_100SEED.md). Earlier run commands remain for **reproduction**, not an outstanding run requirement.
