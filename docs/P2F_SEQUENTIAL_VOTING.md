# P2F — Repeatable Batch vs Sequential Global Greedy Voting
> **Status 2026-10-16: Formal terminal log completed; Sequential is rejected from the main comparison.** The user's Mac log reports 359/359 full tests and 2,000/2,000 formal cases with 100/100 assignments. All 1,000 paired seed/loss comparisons show Sequential emitted more sender Bytes and required more modeled stop time than repeatable Batch Voting, with no task-coverage benefit. Original `per_seed_p2f.csv` / manifest ZIP is not yet uploaded and success-only assignment quality is not audited. **Do not rerun or promote this study to the bilingual README as a main method; retain the original local ZIP/raw evidence and the experimental branch for reproducibility.** The commands below are archival reproduction instructions only, not pending work required for a new formal run. Canonical §56 contains the grouped terminal-log measurements.


Experimental branch: `experiment/p2f-sequential-global-greedy-voting`.

Both native Proposed variants permit up to 300 decision epochs; there is no one-shot method in this A/B. `batch` repeatedly votes on all remaining tasks; `sequential` votes on one still-pending task, commits, removes its executor, then recomputes local Global Greedy for the remaining scene. A failure to collect a vote rotates the pending task and retries. Both use physical one-time original Cost broadcasts and lossy Vote; no hidden information. Original CBAA/CBBA/Centralized source and old P2E evidence remain untouched.

## 1. Mac checkout and tests

```bash
cd "$(git rev-parse --show-toplevel)"
git status --short
git fetch origin
git switch experiment/p2f-sequential-global-greedy-voting
git pull --ff-only
git rev-parse HEAD
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p2f*.py' -v
python3 -m unittest discover -s tests -v
```

Do not execute formal if any test fails. No new .venv or CI required.

## 2. Paired 0%, 90% smoke (8 new cases)

```bash
P2F_SMOKE="results/p2f_smoke_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2f_sequential_voting \
  --losses 0.00,0.90 --seeds 2 --output-root "$P2F_SMOKE"
```

Expected evidence: 8 trials, 4 summary groups, original Cost exactly 100 sender broadcasts per method case (100 x 816B) regardless of drop, physically emitted sender Bytes equal sum across TASK/Cost/Vote/Score/Commit. At PL0 both native modes must complete 100 tasks with one-to-one Commit. Original batch should finish in one epoch; sequential may need 100+ epochs if a task receives no eligible vote and must rotate. At PL90 incomplete trials must retain attempted sender Bytes and stop time, but must not fabricate a full-assignment cost.

## 3. 0%-loss 100-seed acceptance

```bash
P2F_ZERO="results/p2f_zero_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2f_sequential_voting \
  --losses 0.00 --seeds 100 --output-root "$P2F_ZERO"
```

Require 200/200 complete native cases and zero source/contract errors. The two methods are not required to produce the same assignment because one follows sequential commitments. If this condition or unit tests fail, do NOT promote to formal or the paper.

## 4. Formal paired 100-seed, only after both gates pass

```bash
set -o pipefail
P2F_FORMAL="results/p2f_formal_100seed_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2f_sequential_voting \
  --formal --seeds 100 --output-root "$P2F_FORMAL" \
  2>&1 | tee "$P2F_FORMAL.log"
```

2,000 new native cases; 20 mode/loss groups. The original append-only raw file `per_seed_p2f.csv`, `summary_p2f.csv`, `p2f_comparison_summary.json`, `run_config_p2f.json`, `manifest_p2f.json` hold provenance; JSON is summary data, not a visualization. The physical modeled time is **all-seed stop time**, not successful allocation time for incomplete native cases.

Do not conceal unsuccessful seeds; do not divide all-seed Bytes/time by successful seeds only. Incomplete quality stays blank. Bytes are physically **attempted** sender payload including dropped deliveries. The reference is the same full-information Global Greedy cost, which is not Hungarian optimum.

For interrupted-only runs, use the same output directory, exact Git SHA and arguments with `--resume`. Do not resume a finished folder.

## 5. Archive

```bash
test -f "$P2F_FORMAL/manifest_p2f.json"
zip -j "$HOME/Downloads/p2f_global_greedy_sequential_vs_batch_100seed.zip" \
  "$P2F_FORMAL/per_seed_p2f.csv" \
  "$P2F_FORMAL/summary_p2f.csv" \
  "$P2F_FORMAL/p2f_comparison_summary.json" \
  "$P2F_FORMAL/run_config_p2f.json" \
  "$P2F_FORMAL/manifest_p2f.json" \
  "$P2F_FORMAL.log"
shasum -a 256 "$HOME/Downloads/p2f_global_greedy_sequential_vs_batch_100seed.zip"
```

Send the exact native ZIP to audit before any bilingual README or paper graph update. If the new mode cannot meet the defined gates, retire the experimental branch and do not present its unverified study as an accepted result. Preserve failure log and original historical data.
