# P2D One-Shot Centralized Method — Mac Local Validation and Formal Run

**Status:** executable P2D source is committed on branch `experiment/p2d-centralized-one-shot`; its tests/formal results have **not yet been executed by the source author in this restricted environment**. The user's Mac run and original ZIP independent audit are required before publication. No CI requested.

## Exact scientific comparison

- Main plots: Proposed Method (original P2-C native Voting), CBAA, CBBA, Centralized Method. Price Auction excluded from P2D only.
- Full-Info Greedy is a *black dashed* offline reference in native-completion (100%) and quality (cost ratio 1.0) panels only. It is not a fifth transmitting method or the Hungarian optimum.
- Exactly one physically charged Cost unicast per non-coordinator robot, no Cost retransmission, retry, control recovery or second allocation epoch. Incomplete central assignments remain incomplete; each failed Cost still incurs sender bytes and radio airtime.
- 100R100T / C1 / original paired seeds 0..99, p_loss 0,0.1,...,0.9. P2D executes only 1,000 new Centralized cases; 3,000 P2-C/P2 native comparator rows are source verified and reused.

## 1. Prepare local files and branch

Run from the existing Git checkout of `Democracy-based-Task-Allocation-in-a-Large-scale-Multi-robot-System`:

```bash
git status --short
git fetch origin
git switch experiment/p2d-centralized-one-shot
git pull --ff-only
git rev-parse HEAD

P2C_ZIP="$HOME/Downloads/p2c_global_greedy_100seed.zip"
P2_ZIP="$HOME/Downloads/p2_loss10_100seed.zip"
test -f "$P2C_ZIP" || { echo "MISSING: $P2C_ZIP"; exit 1; }
test -f "$P2_ZIP" || { echo "MISSING: $P2_ZIP"; exit 1; }

shasum -a 256 "$P2C_ZIP" "$P2_ZIP"
```

Expected SHA256 values in order:
- P2-C original Voting ZIP: `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055`.
- P2 original four-algorithm ZIP: `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`.

These ZIP inputs are read-only. Wrong ZIP or incomplete archive raises an original-source `dependency` or `contract` diagnostic *before any new formal execution*.

## 2. All new and full regression tests (NO CI)

```bash
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2d*.py' -v
python3 -m unittest discover -s tests -v
```

Do NOT proceed to formal runs until these tests pass. Share any failing full test traceback and the `git rev-parse HEAD`.

## 3. Fast packet-loss smoke

```bash
P2D_SMOKE="results/p2d_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2d_centralized \
  --losses 0.00,0.90 --seeds 2 \
  --p2c-voting-zip "$P2C_ZIP" \
  --original-p2-zip "$P2_ZIP" \
  --output-root "$P2D_SMOKE"
```

Expect `P2D_COMPLETE new=4 original=12 groups=8`. 0% loss Centralized MUST exactly match all-visible Global Greedy. At 90%, any missing Cost row must not be fabricated. New `per_seed_p2d.csv` records attempted Cost bytes and task coverage (not successful quality for incomplete native runs).

## 4. Zero-loss 100-seed acceptance

```bash
P2D_ZERO="results/p2d_zero_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2d_centralized \
  --losses 0.00 --seeds 100 \
  --p2c-voting-zip "$P2C_ZIP" \
  --original-p2-zip "$P2_ZIP" \
  --output-root "$P2D_ZERO"
```

Require 100/100 Centralized native full-commit and exact per-seed full-information Global Greedy pairing, with one one-time 99 Cost unicast phase, one decision broadcast and 100 Commit messages per successful run.

## 5. Formal paired 100-seed P2D

```bash
set -o pipefail
P2D_FORMAL="results/p2d_formal_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2d_centralized \
  --formal --seeds 100 \
  --p2c-voting-zip "$P2C_ZIP" \
  --original-p2-zip "$P2_ZIP" \
  --output-root "$P2D_FORMAL" 2>&1 | tee "$P2D_FORMAL.log"
```

Expected complete source: 1,000 new `centralized` cases, 3,000 reused original Voting/CBAA/CBBA cases; 4,000 combined rows, 40 summary rows, all 100 same-scene paired seeds per 10 packet-loss levels. Native results and original hashes must be audited before changing research README.

On an *interrupted* run only, the same executable SHA, config, and exact output root can resume with `--resume` added. Do NOT resume a completed folder or change the code/ZIPs after partial evidence is written.

## 6. Zip evidence for independent audit

```bash
test -f "$P2D_FORMAL/manifest_p2d.json" || { echo "P2D incomplete"; exit 1; }
zip -j "$HOME/Downloads/p2d_centralized_one_shot_100seed.zip" \
  "$P2D_FORMAL/per_seed_p2d.csv" \
  "$P2D_FORMAL/per_seed_p2d_combined.csv" \
  "$P2D_FORMAL/summary_p2d.csv" \
  "$P2D_FORMAL/p2d_four_panel.svg" \
  "$P2D_FORMAL/run_config_p2d.json" \
  "$P2D_FORMAL/manifest_p2d.json" \
  "$P2D_FORMAL.log"
shasum -a 256 "$HOME/Downloads/p2d_centralized_one_shot_100seed.zip"
```

Upload the original new ZIP to ChatGPT for raw audit. Publication figure intentionally omits Price Auction. Do not conflate modeled native stop with equal global consensus guarantees, or no-retry central failure with a proven generic centralized-algorithm limitation.
