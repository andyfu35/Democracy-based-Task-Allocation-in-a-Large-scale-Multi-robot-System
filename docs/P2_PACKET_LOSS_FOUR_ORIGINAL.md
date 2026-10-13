# P2 — Four original algorithms, capacity-one packet-loss robustness

Status: source implemented; **user-local revised 4,000-case execution NOT yet completed**. Do not claim completed formal results. This reuses true native algorithms from P1 without modifying a native protocol, global STOP, wire size, safety guard, optimization policy, or read-only first-feasible measurement.

## Preregistered test

- 100 robots, 100 tasks; each robot assigned at most 1 task; same deterministic 100m paired geometry for each Seed 0..99.
- Exactly four native methods: `voting`, `cbaa`, `cbba`, `price_auction`. Exclude `voting_multitask` and team-authored Paid CBAA E9K from *official P2 comparisons*. Preserved P1 five-way original archive unchanged.
- Packet loss: 0.00, 0.10, ... 0.90 (10 points) on original method-native lossy packet classes, independent receiver drop. Reliable TASK and original Voting Score/Commit remain as in P1.
- 10 loss points × 4 methods × 100 paired Seeds = **4,000** original simulated method-cases.
- Model: sampled original Rady ROS application delays plus **hypothetical 144 Mbps** shared-medium service; not measured physical RF.
- Native guards: original Voting 300, other native methods 160. Price epsilon 10m. Same owner and state transitions as P1; no new wrapper STOP, no new Paid CBAA.
- Independent read-only observer captures first *externally* feasible full unique assignment following an originally paid native phase. Native completion is a separate indicator: paid Voting reliable Commit versus CBAA local proof / simulator halt, CBBA observer halt, Price Auction optimistic local halt. Thus do **not** interpret stop time as equal distributed terminal knowledge.

## Superseded five-percent formal attempt (do not mix evidence)

The earlier P2 code used 5-point-percentage intervals (19 PL values, 7,600 method-cases). The user started a local formal run on that older source; the supplied terminal excerpt includes a partial 0% cohort. **Do not overwrite or reclassify that original partial run as completed 10% evidence.** Stop the old process with Ctrl+C before updating the branch, preserve its CSV/log/metadata as historical evidence, and use a **brand-new output root** for the revised 10% formal execution. Even shared PL cells (0%, 10%, ...) must be executed and SHA-attested under the new 10% source contract; the old directory cannot be resumed with this new SHA/config. Any later finer resolution is a separately scoped follow-up experiment.

## Four-panel single source figure

1. Native complete cases / all 100 seeds, retaining guards and native failures in the denominator.
2. Mean native modeled stop seconds only if all 100 native time records exist; blanks are **missing**, never zero. Failure/guard counts stay beside time.
3. Mean **attempted** sender application Bytes including dropped sends, only if all 100 native sender records exist; not successful received payload and not real Wi-Fi airtime.
4. Euclidean cost/Hungarian optimum on the **intersection of the four native-success paired seeds per loss point**; separately report `same_four_success_seeds`. No missing auction cases silently removed from success rates.

Produce `per_seed_p2.csv` (append, flush, fsync), `summary_p2.csv`, `packet_loss_robustness.svg`, `run_config_p2.json`, and SHA256-attested `manifest_p2.json`. Preserve source Git SHA and original first-failure method diagnostics. A partial run can resume only with `--resume` and matching SHA/config/exact existing prefix; never overwrite a completed run.

## Mac test / formal commands (NO CI)

From project root on branch `experiment/p2-cap1-loss-robustness`:

```bash
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p1_*.py' -v
python3 -m unittest discover -s tests -p 'test_p2_*.py' -v

# Zero-loss, 2 paired seeds; no formal figure/manifest assumptions
python3 -m experiments.run_p2_packet_loss \
  --losses 0.00 --seeds 2 \
  --output-root "results/p2_loss0_smoke_$(date +%Y%m%d_%H%M%S)"

# Representative P1 matched 30% and high-loss 90%, 2 seeds
python3 -m experiments.run_p2_packet_loss \
  --losses 0.30,0.90 --seeds 2 \
  --output-root "results/p2_loss30_90_smoke_$(date +%Y%m%d_%H%M%S)"

# Formal 4,000 cases, four ORIGINAL methods, all 10 loss points:
set -o pipefail
P2_ROOT="results/p2_four_original_100r100t_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2_packet_loss \
  --formal --seeds 100 --output-root "$P2_ROOT" 2>&1 | tee "$P2_ROOT.log"
test -f "$P2_ROOT/manifest_p2.json" && \
  zip -r "$HOME/Downloads/p2_four_original_loss_sweep_100seed.zip" "$P2_ROOT" "$P2_ROOT.log"
```

If interrupted, repeat the formal command with the **same P2_ROOT** plus `--resume`, and a new log target; the already stored complete-case prefix is not recomputed.

### Acceptance checks

Recompute from uploaded original ZIP: exact 40 summary rows, exactly 4,000 raw records, full paired 100 Seeds at each of 10 PL values; source/manifest/hash/scene checks, native SEND/Bytes/drop/phase ledgers where available, every original failure retained, partial evidence explicitly missing. Cross-check P2 30%-loss 100R/100T cell against the original independently audited P1 results **with attention to differing source SHA**. Publish B panel only after ZIP audit; do not assert P1/P2 values identical before running.

### Diagnostic boundaries

Runner: `validate_config data/P2_INVALID_LOSS_GRID`, `data/P2_INVALID_SEED_RANGE`, `contract/P2_FORMAL_GRID_NOT_FROZEN`; `prepare_evidence state/P2_OUTPUT_EXISTS,P2_INVALID_RESUME_STATE`, `contract/P2_RESUME_CONFIG_MISMATCH,P2_RESUME_FIELDS_CHANGED,P2_RESUME_INVALID_PREFIX`; `validate_complete_grid contract/P2_INCOMPLETE_OR_DUPLICATE_GRID,P2_SCENE_NOT_PAIRED`. Plotter: `validate_plot_source contract/P2_INCOMPLETE_FOUR_METHOD_PLOT,P2_INVALID_PLOT_DENOMINATOR,P2_MISMATCHED_QUALITY_COHORT`; `panel data/P2_NONFINITE_PLOT_VALUE`. Native first failure belongs to P1's original owner/function/category/code and must not be overwritten.
