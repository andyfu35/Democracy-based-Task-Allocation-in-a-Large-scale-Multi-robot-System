# P2G — Two large figures: one batched task-ordered Greedy versus repeatable Global Greedy

Branch: `experiment/p2g-two-family-voting-comparison`. **This revised native experiment has NOT run on the user's Mac yet.** Do not present results as measured or overwrite original P2/P2D/P2E/P2F evidence.

### Figure 1 — One Shot, T0 → T99 task-ordered Greedy

Two new original native method arms:
- `task_ordered_vote_once` = Proposed: each voter greedily plans **once** in ascending task order, taking only the physically received Cost rows; removes each locally selected candidate from its own plan, then sends **one Vote broadcast containing the full batch of task/candidate pairs**. Positive physically received votes generate paid reliable Score; the resolution owner visits T0,T1,... and selects highest received score among still-free robots, with robot-ID tie-break; emits paid Commit. `max_rounds=1`, `vote_repetitions=1`, `cost_repetitions=1`. No new communication round after unresolved tasks. **Not** the old 100 sequential physical vote epochs.
- `centralized_task_ordered_once` = original centralized `planning_rule=task_ordered,max_cost_rounds=1`: each remote Cost is sent once to the coordinator, which runs the **same T0,T1,... task-order** greedy over only received rows and sends one paid assignment plus executor Commits. **Do not reuse old Centralized One Shot Global Greedy data**, which has a different planner.

Figure 1 cost increase is referenced to the **same-seed full-information task-ordered Greedy**. Its 0% packet-loss cost reference must agree across methods.

### Figure 2 — Original multi-round methods, Global Greedy cost reference

Four curves:
- `proposed_multi`: original SHA-verified P2E Proposed Batch Global Greedy with fresh Vote/Score/Commit on still-pending tasks in up to 300 decision epochs; original Cost sent once, **no retransmission of lost Cost**.
- `cbaa` / `cbba`: originally verified native iterative methods and their **own** planning/communication, not replaced by Greedy. Their assignment costs are **evaluated against** full-info Global Greedy; they do NOT internally use it.
- `centralized_retry`: original Centralized with `planning_rule=global,max_cost_rounds=300`: only still-unreceived Cost senders retransmit their original Cost packets to the coordinator, paid per SEND including drops; after complete receipt or guard, coordinator runs **one** Global Greedy on actually visible rows and announces assignment and executor Commits.

Figure 2 cost increase is referenced to **same-seed full-information Global minimum-pair Greedy**, a different denominator from Figure 1. Do not compare the y values between figures as if a single optimizer reference were shared.

Each figure is a separate 1800×1240 2×2 SVG, showing (a) true full 100/100 native success rate, (b) cost difference (%) only for fully successful one-to-one cases with sample `n`, (c) modeled all-seed stop/communication time (s), (d) all physically attempted application sender payload kB including Cost/Vote dropped at all receivers. No failed cost imputation. Models use Rady latency with assumed 144Mbps shared wireless medium, not measured RF; original reliable TASK/Score/Commit assumptions remain. Different native CBAA/CBBA convergence/Commit certification must be disclosed.

**3,000 new native executions** = 3 new modes × 10 packet-loss rates (0,10,...,90%) × 100 paired seeds (0..99), 30 newly derived summary groups. Historical P2E Proposed/CBAA/CBBA 3,000 native cases are reused via SHA-verified aggregate; the old P2D Centralized One Shot 1,000 cases are **not** used in either figure. Two large SVGs are created only after the full formal run passes source/contract gates.

## 1. Mac original repository: compile and targeted/full regression

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

Do NOT execute formal if a focused or full test fails. Report the **first** failure owner/function/category/code and actual traceback so the true owner can be fixed before new data collection.

## 2. Smoke: PL0 and PL90, 2 seeds, 3 methods = 12 new cases

```bash
P2G_SMOKE="results/p2g_task_order_smoke_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2g_two_figures \
  --losses 0.00,0.90 --seeds 2 \
  --output-root "$P2G_SMOKE"
```

Acceptance: 12 native rows, 6 method/loss groups; at PL0 both task-order arms produce all 100 pairs and same total cost as full-info task-order baseline; central Global retry produces all 100 pairs at Global Greedy reference cost. Every Proposed task-order attempt has exactly one native voting epoch and 100 single batched Vote SENDs (one per robot), no Cost retransmission. Central task-order One Shot has 99 Cost SENDs, central retry sends more when physically missing Cost, no hidden Cost repair. Physical SENDs including losses must be charged.

## 3. Zero-loss 100 seeds: 300 new native cases

```bash
P2G_ZERO="results/p2g_task_order_zero_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2g_two_figures \
  --losses 0.00 --seeds 100 \
  --output-root "$P2G_ZERO"
```

Require 300/300 100-task native paid Commit completions, no duplicate executor/task; all three methods must achieve their appropriate *own* full-info Greedy cost (task order or global). The source/contract acceptance gate is `P2G_ZERO_LOSS_FAILED` on incomplete success.

## 4. Formal paired 100 Seed: 3,000 new method runs and 2 SVG files

```bash
set -o pipefail

P2G_FORMAL="results/p2g_task_order_two_figures_$(date +%Y%m%d_%H%M%S)"

python3 -m experiments.run_p2g_two_figures \
  --formal --seeds 100 \
  --output-root "$P2G_FORMAL" \
  2>&1 | tee "$P2G_FORMAL.log"
```

Expected files: `per_seed_p2g.csv` (3,000 fresh rows; exactly 30 method/loss groups in `summary_p2g.csv`), `figure1_task_ordered_one_shot.svg`, `figure2_repeatable.svg`, `run_config_p2g.json`, `manifest_p2g.json`. The historical P2/P2E aggregate is SHA-pinned, not mislabeled as newly executed. Figures are not promoted to either README without an independent native/raw provenance audit.

## 5. Package the original immutable artifacts for review

```bash
test -f "$P2G_FORMAL/manifest_p2g.json" &&
zip -j "$HOME/Downloads/p2g_task_order_and_global_repeat_100seed.zip" \
  "$P2G_FORMAL/per_seed_p2g.csv" \
  "$P2G_FORMAL/summary_p2g.csv" \
  "$P2G_FORMAL/figure1_task_ordered_one_shot.svg" \
  "$P2G_FORMAL/figure2_repeatable.svg" \
  "$P2G_FORMAL/run_config_p2g.json" \
  "$P2G_FORMAL/manifest_p2g.json" \
  "$P2G_FORMAL.log"

shasum -a 256 "$HOME/Downloads/p2g_task_order_and_global_repeat_100seed.zip"
```

If interrupted mid-formal, use exactly same branch SHA/args with `--resume` on the incomplete output directory. A fully completed directory with manifest cannot be silently resumed or overwritten. If the scope fails native or verifier tests, retain diagnostics and original evidence and correct only the true owner; never synthesize publication SVGs from unrun seeds.
