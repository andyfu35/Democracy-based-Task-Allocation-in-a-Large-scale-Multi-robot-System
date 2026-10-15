# P2E Proposed Method Re-Decision Ablation — Mac local runbook

**Branch:** `experiment/p2e-redecision-ablation`

**Scope:** Newly run Proposed Method, original minimum-pair Global Greedy, same native code, exactly `max_rounds=1` versus `max_rounds=300`. Fresh `100R/100T`, `0%–90%` packet loss with 10% spacing, `100` identical Seeds per loss, `2,000` new native cases. Does NOT rerun CBAA/CBBA/Centralized, touch P2D comparisons or reuse old source ZIPs.

**Critical:** Never count only successfully *received* bytes. `native_sender_bytes` is the sum of **all physically emitted SEND payload Bytes**, including packets dropped by receivers. Broadcast = one sender SEND, not 100 receiver charges. The newly recorded `*_sender_bytes` values come from the same real `WifiCausalTimingSampler.packet_trace`, not an estimate based on successful delivery.

## 1. Update current repository (keep existing .venv)

```bash
cd "$(git rev-parse --show-toplevel)"
git fetch origin
git switch experiment/p2e-redecision-ablation
git pull --ff-only
git rev-parse HEAD
```

No virtual environment creation and no CI required.

## 2. Syntax, new targeted tests and full regression

```bash
python3 -m compileall -q democracy_mrta experiments tests &&
python3 -m unittest discover -s tests -p 'test_p2e*.py' -v &&
python3 -m unittest discover -s tests -v
```

**Stop on the first error.** Pass/failure is not asserted by the GitHub author without Mac test output. Existing P2D tests must also remain green.

## 3. Small paired loss smoke (8 newly executed cases)

```bash
P2E_SMOKE="results/p2e_ablation_smoke_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2e_redecision_ablation \
  --losses 0.00,0.90 \
  --seeds 2 \
  --output-root "$P2E_SMOKE"
```

Expect `P2E_COMPLETE cases=8 groups=4`, including 0% exact Greedy first-round pairing and 90% first-epoch fingerprint parity between both arms. Compare `task_sender_bytes`, `cost_sender_bytes`, `vote_sender_bytes`, `score_sender_bytes`, `commit_sender_bytes` in `per_seed_p2e.csv`. Cost is 100 full 816 B SENDs = 81,600 sender Bytes **in both variants at every loss**.

## 4. Independent 0%-loss 100-Seed gate (200 newly executed cases)

```bash
P2E_ZERO="results/p2e_ablation_zero_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2e_redecision_ablation \
  --losses 0.00 --seeds 100 \
  --output-root "$P2E_ZERO"
```

Require 100/100 exact complete-information Global Greedy per mode, one native epoch for BOTH arms and equal first-epoch hash, committed pairs, completion time, sender Bytes per same seed.

## 5. Full paired P2E ablation (2,000 NEW native cases)

```bash
set -o pipefail
P2E_ROOT="results/p2e_ablation_formal_100seed_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2e_redecision_ablation \
  --formal --seeds 100 \
  --output-root "$P2E_ROOT" \
  2>&1 | tee "$P2E_ROOT.log"
```

A completed study has:
- `per_seed_p2e.csv` — exactly 2,000 source-pinned method cases and 10 explicit phase SEND count/byte columns.
- `summary_p2e.csv` — exactly 20 groups, separate native full completion and Task Coverage, 1/300 decision epochs, all-seed Sender Bytes and stop time, quality only on natively complete cohorts.
- `p2e_redecision_ablation.svg` — 6-panel native Proposed single/multi decision ablation with no fake failed-quality zeros.
- `run_config_p2e.json` and `manifest_p2e.json` — exact Git commit/config/seed/inputs and SHA256.

**If and only if the run was interrupted:** resume the exact unfinished root without changing the committed source SHA or config:

```bash
python3 -m experiments.run_p2e_redecision_ablation \
  --formal --seeds 100 --resume \
  --output-root "$P2E_ROOT" \
  2>&1 | tee -a "$P2E_ROOT.log"
```

## 6. Upload raw evidence for independent review

```bash
test -f "$P2E_ROOT/manifest_p2e.json" || { echo "P2E incomplete"; exit 1; }
zip -j "$HOME/Downloads/p2e_redecision_ablation_100seed.zip" \
  "$P2E_ROOT/per_seed_p2e.csv" \
  "$P2E_ROOT/summary_p2e.csv" \
  "$P2E_ROOT/p2e_redecision_ablation.svg" \
  "$P2E_ROOT/run_config_p2e.json" \
  "$P2E_ROOT/manifest_p2e.json" \
  "$P2E_ROOT.log"
shasum -a 256 "$HOME/Downloads/p2e_redecision_ablation_100seed.zip"
```

Share the resulting ZIP. Do NOT replace published historical four-method plots with these two-arm results. Interpret comparisons as the **causal effect of allowing extra native decision epochs**, not as packet retransmission and not as proof that centralized and decentralized robustness differ by the same amount.
