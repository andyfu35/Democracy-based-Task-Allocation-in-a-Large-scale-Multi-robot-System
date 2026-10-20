# P2H — True one-task-at-a-time Vote/Commit versus sequential Centralized baseline

New GitHub branch: experiment/p2h-interactive-task-voting-figure1

Do not run the older P2G Figure 1 again or relabel its 100-seed one-batch results. P2H is the fresh interactive sequential Figure 1. The original Figure 2 remains the accepted P2G comparison of Proposed / CBAA / CBBA / Baseline Centralized, except its graphical bottom three explanatory lines are removed (all algorithm evidence remains untouched).

## Precise paired behavior

For Proposed, Cost is broadcast ONCE at the start. For task T0, each active voter chooses its locally cheapest robot and attempts ONE Vote for T0. Received votes produce original reliable Score and executor Commit; the committed robot is retired. T1 is voted only AFTER T0's Commit or unsuccessful vote-window expiration. Continue through T99, attempting each distinct task at most once. If a task was not assigned, it stays unassigned for the remainder of the run. The same original retirement membership owner is used, with max_rounds=100, voting_strategy=greedy_task, vote_decision_rule=received_plurality, Cost/Vote repetitions=1. Note: this is up to 100 actual decision epochs, NOT one total packet or one batch plan, and the original Score/Commit network traffic counts.

For Baseline Centralized, Cost is unicasted ONCE by each of 99 remote robots to coordinator 0. Coordinator knows only timely physically received Cost and its own row; T0 chooses the cheapest remaining visible robot, broadcasts a paid per-task assignment, waits for that executor's paid Commit, retires it, then handles T1. One assignment broadcast is billed for EACH actually assigned task, unlike archived P2G one-batch Centralized. No hidden Cost and no retransmission. Its chosen Greedy baseline is not representative of every centralized MRTA.

Each method uses the same 100R100T capacity-one E0 seed and paired loss rates. Figure 1 has four panels: **(A) average task completion rate**, calculated as 100 × mean_task_coverage (all committed task counts divided by the 100 task opportunities per seed, averaged over all 100 Seeds); **(B)** full-success-only cost increase relative to full-info task-order Greedy; **(C)** all-seed modeled decision/stop seconds; **(D)** all-attempted sender application kB including packets dropped at receivers. The raw and summary CSV still retain the DIFFERENT strict full-100-task Seed success rate as completion_rate_percent/native_complete for separate tables; that strict metric is NOT panel A. Under zero loss, EACH method must complete 100/100 tasks with zero cost increase. Communication values are Rady-sampled + hypothetical 144Mbps shared-medium simulation, not actual WiFi RF measurements.

## Step 1 — update and run the focused + full tests

Activate your existing project venv, enter the repository, and run:

```bash
cd "$(git rev-parse --show-toplevel)"
git status --short
git fetch origin
git switch experiment/p2h-interactive-task-voting-figure1
git pull --ff-only
git rev-parse HEAD

python3 -m compileall -q democracy_mrta experiments tests &&
python3 -m unittest discover -s tests -p 'test_p2h*.py' -v &&
python3 -m unittest discover -s tests -p 'test_p2g*.py' -v &&
python3 -m unittest discover -s tests -v
```

These tests have NOT been run by the assistant through GitHub tools. The assistant does not have shell access to your Mac. If any test fails, stop immediately, keep the first traceback including owner/function/category/code and share it; do not start formal while a contract fails.

## Step 2 — smoke (8 new native cases, 2 seeds × PL0/PL90 × 2 methods)

```bash
P2H_SMOKE="results/p2h_smoke_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2h_sequential_figure1   --losses 0.00,0.90 --seeds 2   --output-root "$P2H_SMOKE"
```

Expected: P2H_COMPLETE cases=8 groups=4 figure=0; at PL0, both native methods 100/100, equal full-info task-order cost, exactly 100 native Proposed task epochs and 100 physically paid per-task Centralized assignment/Commit sends. Native Cost sent one time (Proposed 100 original broadcasts, Centralized 99 remote unicasts). PL90 is allowed to be incomplete, but no duplicate robot/task or duplicated attempted task and no hidden Cost.

## Step 3 — zero-loss gate (200 new cases, 100 seeds × 2 methods)

```bash
P2H_ZERO="results/p2h_zero_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2h_sequential_figure1   --losses 0.00 --seeds 100   --output-root "$P2H_ZERO"
```

Expected P2H_COMPLETE cases=200 groups=2, ALL 100 paired seeds 100/100 and exact zero % cost gap for BOTH true native protocols. A genuine miss fails with structured P2H_ZERO_LOSS_NOT_GREEDY; do not secretly substitute batch fallback.

## Step 4 — formal (2,000 fresh cases, 20 groups and the new Figure 1)

```bash
set -o pipefail

P2H_FORMAL="results/p2h_interactive_figure1_100seed_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2h_sequential_figure1   --formal --seeds 100   --output-root "$P2H_FORMAL"   2>&1 | tee "$P2H_FORMAL.log"
```

Expected P2H_COMPLETE cases=2000 groups=20 figure=1. Files are:
- per_seed_p2h.csv (2,000 original native records, 100 epoch IDs/Commit lists per Proposed case and true physical sender ledger)
- summary_p2h.csv (20 cells with conditional full-success cost sample n, mean all-case time/Bytes and mean task coverage)
- figure1_interactive_sequential.svg (1800x1120, four panels, no bottom explanatory text)
- run_config_p2h.json (source Git SHA, Rady input SHA, complete frozen configuration)
- manifest_p2h.json (per-artifact SHA256)

Formal output and the prior P2G Figure 2 are NOT modified or overwritten by one another.

## Step 5 — ZIP and upload to ChatGPT for independent audit

```bash
test -f "$P2H_FORMAL/manifest_p2h.json" &&
zip -j "$HOME/Downloads/p2h_interactive_figure1_100seed.zip"   "$P2H_FORMAL/per_seed_p2h.csv"   "$P2H_FORMAL/summary_p2h.csv"   "$P2H_FORMAL/figure1_interactive_sequential.svg"   "$P2H_FORMAL/run_config_p2h.json"   "$P2H_FORMAL/manifest_p2h.json"   "$P2H_FORMAL.log"

shasum -a 256 "$HOME/Downloads/p2h_interactive_figure1_100seed.zip"
```

Upload the ZIP. An independent audit will verify task order and uniqueness, centralized per-task Commit timing, Cost/Vote sender-versus-receiver ledger, missing incomplete-case cost, paired scenes and manifest/source SHA before reporting the paper figure. Use the unchanged previously verified P2G Figure 2 (with text removed) alongside the NEW Figure 1. No data is synthesized for unrun trials.

For interrupted formal runs only, resume with the same code SHA, same Rady file hash and same options plus --resume, using the SAME incomplete output directory. Never resume a completed directory that contains manifest_p2h.json; do not overwrite earlier source evidence.


## Replot corrected Figure 1 A from EXISTING formal data — NO experiment rerun

This correction is display-only. The original 2,000 P2H runs and their manifest are immutable. To reproduce the revised *task completion rate* A in a **separately named** SVG using the new plot owner, switch to branch `fix/p2h-figure1-task-completion-axis` and run this from repo root. Replace `RESULT_DIR` with the existing formal result directory that contains `summary_p2h.csv`; this does not execute any native experiment, overwrite the original `figure1_interactive_sequential.svg` or modify its manifest.

```bash
RESULT_DIR="results/p2h_interactive_figure1_100seed_YYYYMMDD_HHMMSS"
python3 - "$RESULT_DIR" <<'PY'
import csv
from pathlib import Path
import sys
from experiments.p2g_plot import render_p2g_figure
root=Path(sys.argv[1])
with (root / "summary_p2h.csv").open(newline="",encoding="utf-8") as f:
    rows=list(csv.DictReader(f))
output=root / "figure1_task_completion_revised.svg"
output.write_text(
    render_p2g_figure(rows,tuple(range(0,91,10)),"interactive"),
    encoding="utf-8",
)
print(output)
PY
```

If only the uploaded ZIP is available, extract the verified `summary_p2h.csv` without touching the original ZIP. No new 100-Seed training/test/experiment is required. The corrected A must show Proposed 100% and Baseline Centralized 50.06% at PL50, and 10.54% for the baseline at PL90. Panels B/C/D and all method-specific raw measurements remain the same. Tests: run `python3 -m unittest discover -s tests -p 'test_p2h*.py' -v`, then `test_p2g*.py`.
