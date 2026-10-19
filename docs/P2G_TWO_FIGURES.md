# P2G — Two large four-panel figures, native 100-Seed study

Branch: `experiment/p2g-two-family-voting-comparison`

This new experiment is NOT yet run on your Mac. It introduces only **2,000 new native cases**, while producing two separate large 1800×1240 SVGs. The already verified historical P2/P2D/P2E 100-seed cohorts are reused with an exact-pinned Git blob/source SHA. Do not reinterpret historical one-shot Centralized as repeated Centralized.

| Figure | Native methods | Allowed repeated communication |
|---|---|---|
| Figure 1, single attempt | Sequential Global Greedy Voting (each task **once**, 100 task opportunities), original P2D Centralized One Shot | No Vote retry or second Cost attempt |
| Figure 2, iterative | Proposed Multi-Round Global Greedy, original native CBAA, original native CBBA, **new** Centralized Cost Retry + Global Greedy | Proposed votes again only on unfinished tasks; Centralized resends Cost only from senders still unseen; CBAA/CBBA retain original native iterative rules |

**Important:** CBAA and CBBA use **their own native planning**, not the Global Greedy algorithm. The same offline full-information Global Greedy is used strictly as a read-only COST denominator for **all** methods. Replacing the CBAA/CBBA internal optimizer with Global Greedy would produce custom variants, not original CBAA/CBBA.

**One-attempt definition:** 100 tasks each can get **one sequential task-voting epoch**, so 100 physical task-epoch opportunities, not one packet for the entire experiment. `batch_vote_scope=one_task,max_rounds=100,vote_repetitions=1`. P2F repeated serial with 300 epochs cannot substitute. If an epoch fails to decide a task, no future epoch of this new study may revisit that same task. At most 100 attempted distinct task IDs. Original one-shot centralized has only one Cost SEND per sender.

**Cost retry definition:** coordinator robot 0 retains successfully received robot Cost rows. Each failed sender unicasts its Cost again in the following retry epoch (up to 300 total Cost attempts). Every SEND is charged even if its Cost packet is dropped. No partial assignment+new planning loop per Cost round; after full Cost receipt or exhausted retry cap, original centralized owner publishes exactly one paid Global Greedy assignment and executor Commits. In particular, `max_cost_rounds=1` keeps original P2D one-shot behavior.

All results use 100 robots, 100 tasks, capacity 1, Rady sampled delays, a hypothetical shared 144Mbps wireless medium, 10 PL points from 0 to 90% inclusive and original 100 paired seeded E0 scenes. No empirical RF measurement. Reliable TASK, Vote Score and Commit are **model assumptions**. Failed cases stay in mean stop-time/sender Bytes, while successful-only cost is missing for native-incomplete cases.

## 1. Checkout and regression gate on Mac

Use your existing virtual environment and original repository root. These tests have **not** been executed by the assistant (GitHub can be edited, but the remote Mac and repo network are unavailable in this runtime).

```bash
cd "$(git rev-parse --show-toplevel)"
git status --short
git fetch origin
git switch experiment/p2g-two-family-voting-comparison
git pull --ff-only
git rev-parse HEAD

python3 -m compileall -q democracy_mrta experiments tests &&
python3 -m unittest discover -s tests -p 'test_p2g*.py' -v &&
python3 -m unittest discover -s tests -v
```

All tests must pass before running the native experiments. If anything fails, preserve and share the **first** traceback and do not continue to formal.

## 2. PL0+PL90 two-seed smoke (8 new native cases)

```bash
P2G_SMOKE="results/p2g_smoke_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2g_two_figures \
  --losses 0.00,0.90 --seeds 2 \
  --output-root "$P2G_SMOKE"
```

Expect 8 paired new-native cases (2 loss points x 2 seeds x 2 methods), 4 summary groups. Check positive Cost/Vote physical SENDs, cost one time for Proposed, Cost retry only for Centralized, strict 100/100 allocation and finite cost at PL0, no invented complete quality at PL90. Old P2D/CBAA/CBBA/Proposed historical data are not re-executed at smoke.

## 3. Zero-loss 100-seed acceptance (200 new native cases)

```bash
P2G_ZERO="results/p2g_zero_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2g_two_figures \
  --losses 0.00 --seeds 100 \
  --output-root "$P2G_ZERO"
```

Both new methods must achieve **100/100 physically valid assigned tasks on all 100 seeds**. The experimental runner stops with diagnostic `P2G_ZERO_LOSS_FAILED` otherwise. This is an explicit study acceptance gate; do not change the algorithm merely to pass.

## 4. Formal 100 seeds, two figures, 2,000 new native cases

```bash
set -o pipefail

P2G_FORMAL="results/p2g_two_figures_100seed_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2g_two_figures \
  --formal --seeds 100 --output-root "$P2G_FORMAL" \
  2>&1 | tee "$P2G_FORMAL.log"
```

Final output:

- `per_seed_p2g.csv` — all 2,000 original newly simulated native rows, including loss/seed, source SHA, each attempted SEND and confirmed Commit count.
- `summary_p2g.csv` — 20 fresh two-arm/loss aggregates and success-only cost `n`.
- `figure1_single_attempt.svg` — large 1800×1240 four-panel graph for Figure 1, Proposed one attempt/task vs Centralized One Shot.
- `figure2_repeatable.svg` — large 1800×1240 four-panel graph for Figure 2, Proposed Multi-Round, native CBAA, native CBBA, Centralized with missing-Cost retransmission.
- `run_config_p2g.json`, `manifest_p2g.json` — actual experiment source, paired layout, original aggregated legacy source provenance, per-artifact SHA256.

Note: the two figure SVGs are produced **only in formal mode**, after all 2,000 native cases are complete and all source/diagnostic gates pass.

## 5. Package for independent review

```bash
test -f "$P2G_FORMAL/manifest_p2g.json" &&
zip -j "$HOME/Downloads/p2g_two_figures_100seed.zip" \
  "$P2G_FORMAL/per_seed_p2g.csv" \
  "$P2G_FORMAL/summary_p2g.csv" \
  "$P2G_FORMAL/figure1_single_attempt.svg" \
  "$P2G_FORMAL/figure2_repeatable.svg" \
  "$P2G_FORMAL/run_config_p2g.json" \
  "$P2G_FORMAL/manifest_p2g.json" \
  "$P2G_FORMAL.log"

shasum -a 256 "$HOME/Downloads/p2g_two_figures_100seed.zip"
```

Upload this ZIP for our independent physical sender-Bytes, native success/cohort counts, and cost-imputation/source-SHA audit. Only after that will we replace the published English and Traditional Chinese README's two B-family primary figures. This new study does not delete, relabel, or rewrite the archived source runs.

For a crash within an incomplete root, use exactly the same source/config and rerun with `--resume --output-root "$P2G_FORMAL"` (and the original `--formal --seeds 100`). A completed root/manifest rejects resume; use a new root if intentionally starting a genuinely new experiment.
