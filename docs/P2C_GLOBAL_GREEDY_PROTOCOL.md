# P2-C — Global minimum-pair Greedy Voting, capacity one (2026-10-13)

**Status: independently verified P2-C formal native simulation complete (2026-10-13).** The experiment branch `experiment/p2-global-greedy-voting` code was executed at exact Git SHA `8038370205d586c697295b42eb255812be7aa88e`; the user supplied an original 1,705,448-byte ZIP SHA256 `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055`. Its full native Vote/Score/Commit results passed **0% loss Global Greedy 100/100 exact pair checks**, and the complete **1,000 new Voting + 3,000 unchanged original baseline / 4,000 combined** source audit had **zero errors in 71,156 independent validations**. The offline oracle alone is no longer the only evidence. [Formal results and limitations](P2C_FORMAL_100SEED.md).

## Single bounded algorithmic modification

The current accepted P2-B result (ZIP SHA256 `acd3dd389303a58cb27a16f46f29b6008f8b4678ff786d249e13caf60d61c08a`, executed source `7c082610bb3e3489ab09d07aaa339d1bbcd9acaa`) used ascending-Task-ID Greedy. The user explicitly requests **Global Greedy** to remove 0%-loss allocation bias and make a native-to-native comparison more meaningful.

The **planner's owner function** `democracy_mrta.optimizer.solve_visible_batched_greedy_assignment` now ranks all pairs **(cost, task_id, robot_id)** among the currently *physically visible* Cost rows and *all* currently pending tasks. Take the lowest cost pair, remove both endpoints, and repeat. Each local ballot is a one-to-one list. Do **not** fetch missing Cost rows, introduce Hungarian, perform two-opt, change Cost definitions, or use centralized state. This planner is Global Greedy on **each local physical view**, not a guarantee of global optimality under loss.

The **Score decision owner function** `democracy_mrta.coordination.resolve_capacity_one_batch_winners` now orders *all genuinely received candidate Score edges* by descending received vote count, then task ID and robot ID as deterministic tie-breakers, and greedily excludes already committed task and robot within the batch. Compared with previous ascending-Task-ID *winner resolution*, the largest received vote-count proposal wins first even for a later task. **Score is not a distance vector**; no undelivered Cost, global central optimizer, or unbilled extra packet is used. Ties may still prefer lower task IDs, which must be stated when discussing high-loss quality.

Preserved original true owners/semantics: a single reliable logical announcement of all 100 TASK positions (physically **3 frames** under this model), one full 100-task Cost broadcast **per robot per run** (100 original physical SEND frames, never recomputed/sent per epoch), lossy receiver Vote, one batched Vote per active robot per epoch, reliable scored candidate vector, reliable one-to-one per-executor Commit, existing original retirement membership/retry state machine, modeled original Rady application delay and hypothetical shared 144 Mbps, Vote/Score 1200B frame limit, 300 Voting guard and all native baseline stops/guards. The original `greedy_task` P1 mode and the SHA-attested P2-B raw evidence remain unchanged on their historical branches.

## Frozen evaluation / first diagnostic

**Phase 1: only 0%-loss 100R/100T/C1 × Seeds 0..99 (100 freshly simulated Voting cases).** `experiments.run_p2_packet_loss.validate_batched_voting_evidence` now requires **the exact all-robots-visible Global Greedy pairing** on each 0%-loss Seed, a single Vote/Score epoch, full native completion, exactly 100 one-time Cost SENDs, the correct number of framed initial TASK SENDs, exactly one reliable Commit per actual pairing and additively consistent TASK+Cost+Vote/Score+Commit native time. The first contract diagnostic for wrong assignment is now `owner=experiments.run_p2_packet_loss / function=validate_batched_voting_evidence / category=contract / code=P2_GLOBAL_GREEDY_NO_LOSS_MISMATCH` with expected/actual pairs. `optimizer.solve_visible_batched_greedy_assignment` adds `planning/GLOBAL_GREEDY_CARDINALITY_MISMATCH`; all previous data/state diagnostics remain intact. `protocol.validate_one_to_one_commits` still owns duplicate executor/task safety.

**Independent offline 0% oracle, already completed:** 100 deterministic 100m scenario Seeds, 100 robots and 100 tasks, independently ranked all 10,000 edges per seed. Global minimum-pair Greedy mean cost/Hungarian = **1.2352608182858986**, expected mean total distance = **1260.8468915753372 m**. Historical P2-B Task-ID Voting mean cost/Hungarian = **1.3511949850163498**, mean distance **1375.4837254424779 m**. Original P2 native CBAA and CBBA pairings at 0% are exactly Global Greedy for **100/100 Seeds each**. These are **reference offline cost results only**, not newly measured Voting's 0%-loss native completion, bytes or timing. The offline CSV `p2c_global_greedy_zero_loss_100seed_oracle.csv` is an independent local derived analysis outside the repository and is not represented as original GitHub formal experimental evidence.

**Phase 2, only after Phase 1 passes:** Voting-only formal original 10% PL resolution (0%,10%,...,90%), 100 Seeds × 10 loss points = **1,000 new Voting simulations**; preserve and source-attest existing **3,000** CBAA/CBBA/Price Auction rows from original verified baseline ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9` (source Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`), *without any baseline execution*. Recombine 4,000 source-attributed rows; recompute 40 groups and all four P2 panels A (completion with visible overlap), B (modeled native stop), C (attempted sender Bytes), D (conditional quality relative to Hungarian), always record success sample denominators and 0%-loss Global Greedy reference cost. In particular, **do not** assert high-loss Voting time, completion, network behavior or cost from offline Greedy alone.

## Local Mac verification and rerun — no CI

From your checked-out repository, keeping the old P2B archive and README unmodified:

```bash
git fetch origin
git switch experiment/p2-global-greedy-voting
git pull --ff-only
python3 -m compileall -q democracy_mrta experiments tests
python3 -m unittest discover -s tests -p 'test_p1_*.py' -v
python3 -m unittest discover -s tests -p 'test_p2_*.py' -v

# Mandatory revised 0%-loss 100 Seed native acceptance, 100 Voting simulations only.
P2C_ZERO="results/p2c_global_greedy_zero_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2_packet_loss \
  --losses 0.00 --seeds 100 \
  --baseline-zip "$HOME/Downloads/p2_loss10_100seed.zip" \
  --output-root "$P2C_ZERO" 2>&1 | tee "$P2C_ZERO.log"

# Only if the 0% acceptance above and the focused regression suite pass:
set -o pipefail
P2C_ROOT="results/p2c_global_greedy_formal_$(date +%Y%m%d_%H%M%S)"
python3 -m experiments.run_p2_packet_loss \
  --formal --seeds 100 \
  --baseline-zip "$HOME/Downloads/p2_loss10_100seed.zip" \
  --output-root "$P2C_ROOT" 2>&1 | tee "$P2C_ROOT.log"
test -f "$P2C_ROOT/manifest_p2.json" && \
  zip -r "$HOME/Downloads/p2c_global_greedy_voting_100seed.zip" \
    "$P2C_ROOT" "$P2C_ROOT.log"
```

If interrupted, use `--resume` only for the **exact same code SHA**, run-root, 10% full grid, original baseline archive and seed configuration. Never append new Global Greedy results to the older P2-B Task-ID Voting CSV or alter any user-provided original baseline CSV. The 0% 100-Seed preliminary run is deliberately independent and is not mixed into the formal 1,000-case sample; both can be archived under separate folders.

**Required acceptance before README B replacement:** exact 100/100 0%-loss native Global Greedy pairs and one-epoch completion; 1,000 complete new original Voting rows, exactly 3,000 SHA-pinned unchanged baseline rows and 4,000 combined records with new/old source Git identifiers; Cost one-time and framed TASK sender audit, valid real vote receipts and Score/Commit one-to-one, original sender Bytes and staged time additivity; 40 native grouped summary rows and four-panel SVG independently derived and checked. Publication labels should use `Voting (Global Greedy)`, `CBAA`, `CBBA`, `Price Auction` — no "Original" prefixes. Old P2-B main README B graph/results remain historical source evidence until the formal P2-C source ZIP is audited.

**Risks/unverified:** no access to the user's Mac local runtime from this repository editing environment; current offline Global Greedy calculation does not validate the lossy network, Score/Commit execution or new 0%-loss native assignment. Global Greedy is not Hungarian optimal, and high-loss partial local proposals plus Score rank can still produce expensive assignments. External original baselines have different paid-terminal semantics, and Rady sampled app delay / assumed 144Mbps is not measured physical multi-robot Wi-Fi.


## Accepted native P2-C formal result (2026-10-13; supersedes old pending status)

Original user ZIP `p2c_global_greedy_100seed.zip`: SHA256 `f50068e4569771538f3083b8434bc91bce1f42bdec44e8feb74407be90682055`; executed source Git SHA `8038370205d586c697295b42eb255812be7aa88e`; source raw new Voting 1,000 rows SHA256 `a5f6c59837b80596066752c6546a37a387b4ccf177f8d4f1c03c527309a4a5fe`; new+reused 4,000-case combined raw SHA256 `859ad11170a387c6d950b7bde82857e6370b4d1cfa1803b62984090eff698448`; original 40-group summary SHA256 `1f6077ee3ec0deed1ec90b7d90f0b8547330a66b97f12dbc76389bd4dfb722ac`. The unmodified original CBAA/CBBA/Price Auction 3,000-case source remains pinned to ZIP SHA256 `1d08a167308b9368ee2a764737066223ac041a5bd6508621c7b6cd0320036bb9`, source Git `f514cfa3613e7b0bad5c739d136b09fea8c3f92c`. All raw ZIPs remain immutable with their original user source SHA, not replaced by publication data.

**Original 0%-loss native contract confirmed:** `100/100` exact Global Greedy Robot–Task pair matches, `100/100` same native P2-C pairings as original CBAA and original CBBA, complete and Commit-backed in 1 native batched epoch per Seed; Global Greedy/Hungarian ratio mean `1.2352608182858986`, not 1.0. Each new Voting native result is capacity1 and globally one-to-one, all original TASK 3 sender frames and one-time Cost 100 frames recorded, native sender-packet lengths/counts and phase-time additivity verified. **All 1,000 Global Greedy Voting cases are native success across all 10 loss levels**, and 3,000 external native rows are reused byte-for-byte per field. Native total successes=3,270; 3,293 final full feasible observed cases include 23 external baseline rows whose own terminal guards did not accept native full completion. Do not silently reclassify those 23.

**New high-loss modeled result:** PL90 Global Greedy Voting mean STOP `4.493584s` (old P2-B Task-ID `11.742267s`), attempted sender `105.67064 kB` (old `142.00776 kB`), mean Cost/Hungarian `1.296574` (old `3.840376`). PL90 external native CBAA retained 100/100 success, STOP `71.383177s`, sender `14,135.6 kB`, Cost/Hungarian `1.235261`. Cost/Hungarian improves **66.24%** new vs old P2-B at PL90, modeled native stop improves **61.73%**, while Global Greedy remains **4.96% above CBAA** in independent mean cost ratio on same 100 successfully completed seeds. At PL90 average total episodes only **7.34**, down from the old Task-ID **20.78**; original Cost is not repeated. These are **modeled** communications not real Wi-Fi throughput.

**Publication source and cohort contract:** [Full audit report](P2C_FORMAL_100SEED.md), [derived four-panel plot](figures/p2c/formal/p2c_packet_loss_four_panel.svg), [40-group derived plotting source](figures/p2c/formal/verified_40point_summary.csv), [original ZIP SHA and Git evidence](figures/p2c/formal/source_manifest.json). Original runtime SVG uses the all-four-native-success intersection for D; at PL80/90 it is empty. The new publication presentation uses **per-method native-success conditional** cost for D, so Voting/CBAA preserve 100 valid observations; CBBA/Auction remain missing at high PL. It is a **different reported estimator**, not silently equivalent to the original figure; this is explicitly labeled and original runtime SVG remains immutable. Overlapping A uses concentric rings with no shifted data, B/C use log y. Histogram/task fairness: Task0–19 vs Task80–99 original Task-ID `5.66m / 33.06m`, new Global Greedy `12.89m / 12.92m` at PL0.

**Scientific limitations/preservation:** no Hungarian assignment used internally, no CBAA/CBBA/Price rerun, no original P2-B prior ZIP overwritten, no executable change since source Git `80383702`; robust within fixed loss and 144Mbps/Rady model only. Original reliability assumptions (reliable TASK/Score/Commit, lossy Cost/Vote), unequal terminal guarantees and 300 vs160 guards remain. Independent audit validates the native files; it is not a claim of running unrelated full repository CI. **Next research:** examine independent role of local Global Greedy planning vs received-Score priority through ablations and test burst-loss/unreliable Score and multiple N/T ratios; these are NOT necessary for accepting this fixed P2-C formal result.
